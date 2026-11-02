with open(r'D:\vcos1\workspace\vcos\backend\app\intelligence\canonical_mutation.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

lines = content.split('\n')

# Find class CanonicalMutationBoundary
start_idx = -1
for i, line in enumerate(lines):
    if 'class CanonicalMutationBoundary:' in line:
        start_idx = i
        break

if start_idx == -1:
    print('Could not find class CanonicalMutationBoundary')
    exit(1)

# Find the end of the mutate method - look for the next method or class
end_idx = -1
for i in range(start_idx + 1, len(lines)):
    stripped = lines[i].lstrip()
    if stripped.startswith('async def ') or stripped.startswith('def ') or stripped.startswith('class '):
        if not lines[i].startswith('        ') and not lines[i].startswith('    '):
            end_idx = i
            break

print(f'start_idx={start_idx}, end_idx={end_idx}')

# Create new mutate method
new_method = '''    async def mutate(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        target_entity_type: str,
        mutation_type: MutationType,
        target_id: Optional[str] = None,
        mutation_fn: Callable = None,
        expected_version: Optional[int] = None,
        fingerprint: Optional[str] = None,
        provenance: dict = None,
        epistemic_status: EpistemicStatus = EpistemicStatus.PROPOSED,
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
        required_permissions: Optional[list[str]] = None,
        target_organization_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        entity: Optional[Any] = None,  # For CREATE mutations: the new entity
    ) -> MutationResult:
        """Execute a canonical mutation through the boundary."""
       
        # Build context
        permissions = await caller.get_permissions(db) if db is not None else frozenset()
        context = CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=permissions,
            target_entity_type=target_entity_type,
            target_id=target_id,
            mutation_type=mutation_type,
            expected_version=expected_version,
            fingerprint=fingerprint,
            provenance=provenance or {},
            epistemic_status=epistemic_status,
            source_event_id=source_event_id,
            trigger_reason=trigger_reason,
        )

        # 4. Execute mutation with all validations
        async def mutation_wrapper(db: AsyncSession) -> MutationResult:
            print(f"DEBUG mutate: mutation_wrapper called for {target_entity_type}, mutation_type={mutation_type}, target_id={target_id}, fingerprint={fingerprint}")
            
            # Initialize concurrency components
            concurrency_coordinator = CanonicalConcurrencyCoordinator(db)
            idempotency_manager = IdempotencyKeyManager(db)
            optimistic_manager = OptimisticConcurrencyManager(db)
            
            # Create concurrency context
            concurrency_context = ConcurrencyContext(
                operation_id=str(uuid.uuid4()),
                entity_type=target_entity_type,
                entity_id=target_id or "",
                actor_id=caller.user_id,
                organization_id=caller.organization_id,
                concurrency_type=ConcurrencyControlType.OPTIMISTIC,
                expected_version=expected_version,
                fingerprint=fingerprint,
                max_retries=3,
                retry_delay=0.1,
                timeout=30.0,
            )
            
            # Initialize concurrency coordinator
            canonical_concurrency = CanonicalOperationConcurrency(db)
            canonical_concurrency.optimistic = OptimisticConcurrencyManager(db)
            canonical_concurrency.leases = LeaseManager(db)
            
            # 1. Governance validation
            await validate_governance(
                db=db,
                caller=caller,
                target_entity_type=target_entity_type,
                target_id=target_id,
                target_organization_id=target_organization_id or caller.organization_id,
                required_permissions=required_permissions,
            )
            print(f"DEBUG mutate: passed governance validation")
            
            # 2. Target resolution through accessible IDs
            if target_id and target_entity_type not in ["Organization", "User"] and db is not None:
                # Fetch the User object for resolve_accessible_ids
                from app.models.user import User as UserModel
                user_obj = await db.get(UserModel, caller.user_id)
                if not user_obj:
                    raise ScopeViolation(f"User {caller.user_id} not found")
                accessible = await resolve_accessible_ids(
                    db=db,
                    user=user_obj,
                    organization_id=caller.organization_id,
                    kind=_entity_type_to_kind(target_entity_type),
                    ids=[target_id],
                )
                if target_id not in accessible:
                    raise ScopeViolation(
                        f"Target {target_entity_type}:{target_id} not accessible to caller"
                    )
            print(f"DEBUG mutate: passed target resolution")
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            print(f"DEBUG mutate: passed exact-once check")
            
            # Temporal integrity (for both CREATE and UPDATE)
            # For CREATE, pass the entity; for UPDATE, load from DB
            if target_id:
                # UPDATE: load existing entity
                entity_for_temporal = await self._load_entity(db, target_entity_type, target_id)
            else:
                # CREATE: entity is passed as parameter
                entity_for_temporal = entity
            
            await validate_temporal_integrity(
                db=db,
                entity_type=target_entity_type,
                entity_id=target_id,
                entity=entity_for_temporal,
                organization_id=caller.organization_id,
                mutation_type=mutation_type,
                allow_supersession=(mutation_type == MutationType.TRANSITION),
            )
            print(f"DEBUG mutate: passed temporal integrity")
            
            # Provenance validation
            context_obj = CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=target_entity_type,
                target_id=target_id,
                provenance=provenance or {},
            )
            await validate_provenance(db, context_obj)
            print(f"DEBUG mutate: passed provenance validation")
            
            # Epistemic boundary (Gate 6-B: basic promotion rules)
            validate_epistemic_boundary(
                CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    epistemic_status=epistemic_status,
                ),
                epistemic_status,
            )
            print(f"DEBUG mutate: passed epistemic boundary")
            
            # Epistemic integrity (Gate 6-F: comprehensive enforcement)
            await validate_epistemic_integrity(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    epistemic_status=epistemic_status,
                ),
            )
            print(f"DEBUG mutate: passed epistemic integrity")
            
            # Contradiction preservation validation (Gate 6-E)
            await validate_contradiction_preservation(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    metadata={},
                ),
            )
            print(f"DEBUG mutate: passed contradiction preservation")
            
            # Concurrency check
            if target_id and expected_version is not None:
                # Load entity to check version
                entity_for_concurrency = await self._load_entity(db, target_entity_type, target_id)
                if entity_for_concurrency:
                    validate_optimistic_concurrency(entity_for_concurrency, expected_version)
            print(f"DEBUG mutate: passed concurrency check")
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            print(f"DEBUG mutate: passed second exact-once check")
            
            # Execute the actual mutation
            if mutation_fn:
                # For UPDATE mutations, use database-level optimistic concurrency
                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:
                    # Load the model for the entity type
                    type_map = {
                        "CompanyDecision": CompanyDecision,
                        "CompanyAuthorization": CompanyAuthorization,
                        "CompanyCommitment": CompanyCommitment,
                        "CompanyAction": CompanyAction,
                        "CompanyDecisionAlternative": CompanyDecisionAlternative,
                        "CompanyDecisionContradiction": CompanyDecisionContradiction,
                        "CompanyGoal": CompanyGoal,
                        "CompanyObjective": CompanyObjective,
                        "CompanyInitiative": CompanyInitiative,
                        "CompanyIntent": CompanyIntent,
                        "Project": Project,
                        "Task": Task,
                        "Employee": Employee,
                        "User": User,
                        "Organization": Organization,
                    }
                    model = type_map.get(target_entity_type)
                    if model:
                        # Use database-level optimistic update
                        pass
                
                result = await mutation_fn(db)
                print(f"DEBUG mutate: mutation_fn returned result={result}, type={type(result)}")
                
                # For UPDATE mutations, verify the version was actually updated
                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:
                    entity_for_check = await self._load_entity(db, target_entity_type, target_id)
                    if entity_for_check and hasattr(entity_for_check, 'version'):
                        if entity_for_check.version <= expected_version:
                            raise ConcurrencyViolation(
                                f"Stale version: expected {expected_version}, current is {entity_for_check.version}"
                            )
                
                # Mark idempotency key as complete
                if fingerprint:
                    await idempotency_manager.complete(fingerprint, result.id if hasattr(result, 'id') else str(uuid.uuid4()))
                
                return MutationResult(success=True, entity=result, fingerprint=fingerprint)
            else:
                return MutationResult(success=False, error="No mutation function provided")

        try:
            result = await execute_transactional(db, [
                TransactionalMutation(mutation_fn=mutation_wrapper)
            ])
            return result[0] if result else MutationResult(success=False, error="No result")
        except CanonicalMutationError as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
        except Exception as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)'''

# Replace the entire mutate method
new_lines = lines[:start_idx + 1] + new_method.split('\n') + lines[end_idx:]
new_content = '\n'.join(new_lines)

with open(r'D:\vcos1\workspace\vcos\backend\app\intelligence\canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print('Rewrote the mutate method')
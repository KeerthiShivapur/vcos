with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the mutate() method's validation context creation
# The issue is that each validation call creates a new CanonicalMutationContext with missing fields
# We need to create a single complete context and reuse it

old_mutation_wrapper = b'''        # 4. Execute mutation with all validations
        async def mutation_wrapper(db: AsyncSession) -> MutationResult:
            
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
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
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
                    metadata=context.metadata,  # Pass the metadata with updates
                ),
            )'''

new_mutation_wrapper = b'''        # 4. Execute mutation with all validations
        async def mutation_wrapper(db: AsyncSession) -> MutationResult:
            
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
            
            # Build a COMPLETE canonical mutation context for ALL validations
            # This ensures all validation functions receive ALL required fields
            permissions = await caller.get_permissions(db) if db is not None else frozenset()
            full_context = CanonicalMutationContext(
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
                metadata=metadata_dict,
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
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
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
            
            # Provenance validation - use COMPLETE context
            await validate_provenance(db, full_context)
            
            # Epistemic boundary (Gate 6-B: basic promotion rules) - use COMPLETE context
            validate_epistemic_boundary(full_context, epistemic_status)
            
            # Epistemic integrity (Gate 6-F: comprehensive enforcement) - use COMPLETE context
            await validate_epistemic_integrity(db=db, context=full_context)
            
            # Contradiction preservation validation (Gate 6-E) - use COMPLETE context
            await validate_contradiction_preservation(db=db, context=full_context)'''

content = content.replace(old_mutation_wrapper, new_mutation_wrapper)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed mutate() validation contexts")
with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix validate_provenance to properly validate provenance IDs exist and belong to correct tenant
old_validate_provenance = b'''async def validate_provenance(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that mutation has required provenance chain."""
    # Check required provenance based on mutation type and entity
    required_provenance = {
        "CompanyCommitment": ["authorization_id", "decision_id"],
        "CompanyAuthorization": ["decision_id", "policy_id"],
        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],
        "CompanyDecisionAlternative": ["decision_id"],
        "CompanyDecisionContradiction": ["decision_id"],
        "ObjectiveContradiction": ["objective_id"],
        }

    required = required_provenance.get(context.target_entity_type, [])

    for field in required:
        if not context.provenance.get(field) and not getattr(context, field, None):
            raise ProvenanceViolation(
                f"Missing required provenance: {field} for {context.target_entity_type}"
            )

    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity
    # unless this is a supersession (which creates a new version with new provenance)
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing entity to check its provenance
        entity = None
        entity_type = context.target_entity_type
        entity_id = context.target_id
       
        if entity_type == "CompanyCommitment":
            entity = await db.get(CompanyCommitment, entity_id)
        elif entity_type == "CompanyAuthorization":
            entity = await db.get(CompanyAuthorization, entity_id)
        elif entity_type == "CompanyAction":
            entity = await db.get(CompanyAction, entity_id)
        elif entity_type == "CompanyDecisionAlternative":
            entity = await db.get(CompanyDecisionAlternative, entity_id)
        elif entity_type == "CompanyDecisionContradiction":
            entity = await db.get(CompanyDecisionContradiction, entity_id)
        elif entity_type == "ObjectiveContradiction":
            entity = await db.get(ObjectiveContradiction, entity_id)
       
        if entity:
            # Check if this is a supersession (state transition to superseded)
            is_supersession = (
                context.mutation_type == MutationType.TRANSITION and
                context.provenance.get("state") == "superseded"
            )
           
            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":
                # For non-supersession updates, provenance must match
                for field in required_provenance.get(context.target_entity_type, []):
                    provenance_value = context.provenance.get(field)
                    entity_value = getattr(entity, field, None)
                   
                    if provenance_value is not None and entity_value is not None:
                        if provenance_value != entity_value:
                            raise ProvenanceViolation(
                                f"Provenance field '{field}' cannot be changed without supersession. "
                                f"Current value: {entity_value}, attempted: {provenance_value}. "
                                f"Use supersession to change provenance."
                            )
    
    # Cross-tenant and cross-scope provenance validation
    # Only validate for mutations that have entity_id (UPDATE/TRANSITION)
    # For CREATE, the entity doesn't exist yet, so we validate in the mutation_wrapper
    if context.target_id and context.mutation_type != MutationType.CREATE:
        await _validate_provenance_cross_boundaries(db, context)

    return True'''

new_validate_provenance = b'''async def validate_provenance(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that mutation has required provenance chain and all provenance references are valid."""
    # Check required provenance based on mutation type and entity
    required_provenance = {
        "CompanyCommitment": ["authorization_id", "decision_id"],
        "CompanyAuthorization": ["decision_id", "policy_id"],
        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],
        "CompanyDecisionAlternative": ["decision_id"],
        "CompanyDecisionContradiction": ["decision_id"],
        "ObjectiveContradiction": ["objective_id"],
        }

    required = required_provenance.get(context.target_entity_type, [])

    for field in required:
        if not context.provenance.get(field) and not getattr(context, field, None):
            raise ProvenanceViolation(
                f"Missing required provenance: {field} for {context.target_entity_type}"
            )

    # Validate ALL provenance references exist and belong to correct tenant
    # This applies to CREATE, UPDATE, and TRANSITION mutations
    await _validate_provenance_references(db, context)

    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity
    # unless this is a supersession (which creates a new version with new provenance)
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing entity to check its provenance
        entity = None
        entity_type = context.target_entity_type
        entity_id = context.target_id
       
        if entity_type == "CompanyCommitment":
            entity = await db.get(CompanyCommitment, entity_id)
        elif entity_type == "CompanyAuthorization":
            entity = await db.get(CompanyAuthorization, entity_id)
        elif entity_type == "CompanyAction":
            entity = await db.get(CompanyAction, entity_id)
        elif entity_type == "CompanyDecisionAlternative":
            entity = await db.get(CompanyDecisionAlternative, entity_id)
        elif entity_type == "CompanyDecisionContradiction":
            entity = await db.get(CompanyDecisionContradiction, entity_id)
        elif entity_type == "ObjectiveContradiction":
            entity = await db.get(ObjectiveContradiction, entity_id)
       
        if entity:
            # Check if this is a supersession (state transition to superseded)
            is_supersession = (
                context.mutation_type == MutationType.TRANSITION and
                context.provenance.get("state") == "superseded"
            )
           
            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":
                # For non-supersession updates, provenance must match
                for field in required_provenance.get(context.target_entity_type, []):
                    provenance_value = context.provenance.get(field)
                    entity_value = getattr(entity, field, None)
                   
                    if provenance_value is not None and entity_value is not None:
                        if provenance_value != entity_value:
                            raise ProvenanceViolation(
                                f"Provenance field '{field}' cannot be changed without supersession. "
                                f"Current value: {entity_value}, attempted: {provenance_value}. "
                                f"Use supersession to change provenance."
                            )
    
    # Cross-tenant and cross-scope provenance validation
    # Validate for ALL mutation types that have target_id
    if context.target_id:
        await _validate_provenance_cross_boundaries(db, context)

    return True'''

content = content.replace(old_validate_provenance, new_validate_provenance)

# Add new helper function _validate_provenance_references
old_cross_boundaries = b'''async def _validate_provenance_cross_boundaries(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that provenance references don't cross tenant/scope boundaries."""
    entity_type = context.target_entity_type
    entity_id = context.target_id
    caller_org_id = context.caller.organization_id

    # Import all models at the top to avoid UnboundLocalError
    from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
    from app.models.company_operating import CompanyDecision
    from app.models.execution_strategy import CompanyObjective
    from app.models.company_operating import CompanyDecisionAlternative, CompanyDecisionContradiction
    from app.models.execution_strategy import ObjectiveContradiction

    # Load the entity to check its provenance fields
    entity = None
    if entity_type == "CompanyCommitment":
        entity = await db.get(CompanyCommitment, entity_id)
        if entity:
            # Check authorization_id
            if entity.authorization_id:
                auth = await db.get(CompanyAuthorization, entity.authorization_id)
                if auth and auth.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Commitment references Authorization from different organization"
                    )
            # Check decision_id
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Commitment references Decision from different organization"
                    )
    elif entity_type == "CompanyAuthorization":
        entity = await db.get(CompanyAuthorization, entity_id)
        if entity:
            # Check decision_id
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Authorization references Decision from different organization"
                    )
            # Check policy_id
            if entity.policy_id:
                policy = await db.get(ApprovalPolicy, entity.policy_id)
                if policy and policy.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Authorization references Policy from different organization"
                    )
    elif entity_type == "CompanyAction":
        entity = await db.get(CompanyAction, entity_id)
        if entity:
            # Check source_commitment_id
            if entity.source_commitment_id:
                from app.models.execution_strategy import CompanyCommitment
                comm = await db.get(CompanyCommitment, entity.source_commitment_id)
                if comm and comm.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Action references Commitment from different organization"
                    )
                # Cross-scope validation: if both have project scope, they must be in the same project
                if entity.scope_type == "project" and comm.scope_type == "project":
                    if entity.scope_id != comm.scope_id:
                        raise ProvenanceViolation(
                            f"Cross-scope provenance: Action in project '{entity.scope_id}' references Commitment in project '{comm.scope_id}'"
                        )
            # Check source_company_decision_id
            if entity.source_company_decision_id:
                decision = await db.get(CompanyDecision, entity.source_company_decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Action references Decision from different organization"
                    )
    elif entity_type == "CompanyDecisionAlternative":
        entity = await db.get(CompanyDecisionAlternative, entity_id)
        if entity:
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: DecisionAlternative references Decision from different organization"
                    )
    elif entity_type == "CompanyDecisionContradiction":
        entity = await db.get(CompanyDecisionContradiction, entity_id)
        if entity:
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: DecisionContradiction references Decision from different organization"
                    )
    elif entity_type == "ObjectiveContradiction":
        entity = await db.get(ObjectiveContradiction, entity_id)
        if entity:
            if entity.objective_id:
                obj = await db.get(CompanyObjective, entity.objective_id)
                if obj and obj.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: ObjectiveContradiction references Objective from different organization"
                    )

    return True'''

new_cross_boundaries = b'''async def _validate_provenance_references(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that ALL provenance references exist and belong to the correct tenant.
    
    This validates the provenance fields provided in the mutation context itself,
    not the existing entity's fields. This ensures fake/foreign IDs are rejected.
    """
    entity_type = context.target_entity_type
    caller_org_id = context.caller.organization_id
    provenance = context.provenance or {}

    # Define provenance field to model mapping
    provenance_field_models = {
        "authorization_id": ("CompanyAuthorization", CompanyAuthorization, "organization_id"),
        "decision_id": ("CompanyDecision", CompanyDecision, "organization_id"),
        "policy_id": ("ApprovalPolicy", ApprovalPolicy, "organization_id"),
        "source_commitment_id": ("CompanyCommitment", CompanyCommitment, "organization_id"),
        "source_company_decision_id": ("CompanyDecision", CompanyDecision, "organization_id"),
        "objective_id": ("CompanyObjective", CompanyObjective, "organization_id"),
        "source_event_id": ("CompanyDecision", CompanyDecision, "organization_id"),  # For CompanyDecision source_event_id
    }

    # Check each provenance field in the mutation context
    for field, value in provenance.items():
        if value is None:
            continue
            
        if field not in provenance_field_models:
            continue  # Skip fields we don't validate
            
        model_name, model_class, org_field = provenance_field_models[field]
        
        # Look up the referenced entity
        try:
            referenced = await db.get(model_class, value)
        except Exception:
            continue  # Skip if lookup fails
            
        if referenced is None:
            # Referenced entity doesn't exist - this is a fake/foreign ID
            raise ProvenanceViolation(
                f"Invalid provenance: {field}='{value}' references non-existent {model_name}"
            )
            
        # Check tenant isolation
        referenced_org_id = getattr(referenced, org_field, None)
        if referenced_org_id is not None and referenced_org_id != context.caller.organization_id:
            raise ProvenanceViolation(
                f"Cross-tenant provenance: {context.target_entity_type} references {model_name} "
                f"from different organization ({referenced_org_id} != {context.caller.organization_id})"
            )

    return True


async def _validate_provenance_cross_boundaries(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """Validate that provenance references don't cross tenant/scope boundaries.
    
    This validates the EXISTING entity's provenance fields (for UPDATE/TRANSITION)
    to ensure they don't cross tenant boundaries.
    """
    entity_type = context.target_entity_type
    entity_id = context.target_id
    caller_org_id = context.caller.organization_id

    # Import all models at the top to avoid UnboundLocalError
    from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
    from app.models.company_operating import CompanyDecision
    from app.models.execution_strategy import CompanyObjective
    from app.models.company_operating import CompanyDecisionAlternative, CompanyDecisionContradiction
    from app.models.execution_strategy import ObjectiveContradiction

    # Load the entity to check its provenance fields
    entity = None
    if entity_type == "CompanyCommitment":
        entity = await db.get(CompanyCommitment, entity_id)
        if entity:
            # Check authorization_id
            if entity.authorization_id:
                auth = await db.get(CompanyAuthorization, entity.authorization_id)
                if auth and auth.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Commitment references Authorization from different organization"
                    )
            # Check decision_id
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Commitment references Decision from different organization"
                    )
    elif entity_type == "CompanyAuthorization":
        entity = await db.get(CompanyAuthorization, entity_id)
        if entity:
            # Check decision_id
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Authorization references Decision from different organization"
                    )
            # Check policy_id
            if entity.policy_id:
                policy = await db.get(ApprovalPolicy, entity.policy_id)
                if policy and policy.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Authorization references Policy from different organization"
                    )
    elif entity_type == "CompanyAction":
        entity = await db.get(CompanyAction, entity_id)
        if entity:
            # Check source_commitment_id
            if entity.source_commitment_id:
                from app.models.execution_strategy import CompanyCommitment
                comm = await db.get(CompanyCommitment, entity.source_commitment_id)
                if comm and comm.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Action references Commitment from different organization"
                    )
                # Cross-scope validation: if both have project scope, they must be in the same project
                if entity.scope_type == "project" and comm.scope_type == "project":
                    if entity.scope_id != comm.scope_id:
                        raise ProvenanceViolation(
                            f"Cross-scope provenance: Action in project '{entity.scope_id}' references Commitment in project '{comm.scope_id}'"
                        )
            # Check source_company_decision_id
            if entity.source_company_decision_id:
                decision = await db.get(CompanyDecision, entity.source_company_decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: Action references Decision from different organization"
                    )
    elif entity_type == "CompanyDecisionAlternative":
        entity = await db.get(CompanyDecisionAlternative, entity_id)
        if entity:
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: DecisionAlternative references Decision from different organization"
                    )
    elif entity_type == "CompanyDecisionContradiction":
        entity = await db.get(CompanyDecisionContradiction, entity_id)
        if entity:
            if entity.decision_id:
                decision = await db.get(CompanyDecision, entity.decision_id)
                if decision and decision.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: DecisionContradiction references Decision from different organization"
                    )
    elif entity_type == "ObjectiveContradiction":
        entity = await db.get(ObjectiveContradiction, entity_id)
        if entity:
            if entity.objective_id:
                obj = await db.get(CompanyObjective, entity.objective_id)
                if obj and obj.organization_id != caller_org_id:
                    raise ProvenanceViolation(
                        f"Cross-tenant provenance: ObjectiveContradiction references Objective from different organization"
                    )

    return True'''

content = content.replace(old_validate_provenance, new_validate_provenance)
content = content.replace(old_cross_boundaries, new_cross_boundaries)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed validate_provenance and cross-boundaries validation")
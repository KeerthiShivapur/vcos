with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Replace lines 892-966 (0-indexed: 891-965) with new implementation
new_function = [
    b'async def validate_provenance(',
    b'    db: AsyncSession,',
    b'    context: CanonicalMutationContext,',
    b') -> bool:',
    b'    """Validate that mutation has required provenance chain and all provenance references are valid."""',
    b'    # Check required provenance based on mutation type and entity',
    b'    required_provenance = {',
    b'        "CompanyCommitment": ["authorization_id", "decision_id"],',
    b'        "CompanyAuthorization": ["decision_id", "policy_id"],',
    b'        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],',
    b'        "CompanyDecisionAlternative": ["decision_id"],',
    b'        "CompanyDecisionContradiction": ["decision_id"],',
    b'        "ObjectiveContradiction": ["objective_id"],',
    b'        }',
    b'',
    b'    required = required_provenance.get(context.target_entity_type, [])',
    b'',
    b'    for field in required:',
    b'        if not context.provenance.get(field) and not getattr(context, field, None):',
    b'            raise ProvenanceViolation(',
    b'                f"Missing required provenance: {field} for {context.target_entity_type}"',
    b'            )',
    b'',
    b'    # Validate ALL provenance references exist and belong to correct tenant',
    b'    # This applies to CREATE, UPDATE, and TRANSITION mutations',
    b'    await _validate_provenance_references(db, context)',
    b'',
    b'    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity',
    b'    # unless this is a supersession (which creates a new version with new provenance)',
    b'    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):',
    b'        # Load the existing entity to check its provenance',
    b'        entity = None',
    b'        entity_type = context.target_entity_type',
    b'        entity_id = context.target_id',
    b'       ',
    b'        if entity_type == "CompanyCommitment":',
    b'            entity = await db.get(CompanyCommitment, entity_id)',
    b'        elif entity_type == "CompanyAuthorization":',
    b'            entity = await db.get(CompanyAuthorization, entity_id)',
    b'        elif entity_type == "CompanyAction":',
    b'            entity = await db.get(CompanyAction, entity_id)',
    b'        elif entity_type == "CompanyDecisionAlternative":',
    b'            entity = await db.get(CompanyDecisionAlternative, entity_id)',
    b'        elif entity_type == "CompanyDecisionContradiction":',
    b'            entity = await db.get(CompanyDecisionContradiction, entity_id)',
    b'        elif entity_type == "ObjectiveContradiction":',
    b'            entity = await db.get(ObjectiveContradiction, entity_id)',
    b'       ',
    b'        if entity:',
    b'            # Check if this is a supersession (state transition to superseded)',
    b'            is_supersession = (',
    b'                context.mutation_type == MutationType.TRANSITION and',
    b'                context.provenance.get("state") == "superseded"',
    b'            )',
    b'           ',
    b'            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":',
    b'                # For non-supersession updates, provenance must match',
    b'                for field in required_provenance.get(context.target_entity_type, []):',
    b'                    provenance_value = context.provenance.get(field)',
    b'                    entity_value = getattr(entity, field, None)',
    b'                   ',
    b'                    if provenance_value is not None and entity_value is not None:',
    b'                        if provenance_value != entity_value:',
    b'                            raise ProvenanceViolation(',
    b'                                f"Provenance field \'{field}\' cannot be changed without supersession. "',
    b'                                f"Current value: {entity_value}, attempted: {provenance_value}. "',
    b'                                f"Use supersession to change provenance."',
    b'                            )',
    b'   ',
    b'    # Cross-tenant and cross-scope provenance validation',
    b'    # Validate for ALL mutation types that have target_id',
    b'    if context.target_id:',
    b'        await _validate_provenance_cross_boundaries(db, context)',
    b'',
    b'    return True',
]

# Replace lines 892-965 (0-indexed: 891-965) with new function
# Line numbers are 1-indexed in the output above, so 892 is index 891
start = 891
end = 965  # exclusive end

# Read the file
with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Replace lines 891-965 (0-indexed: 891-965) 
# Note: the function ends at line 965 (0-indexed 964) based on output
# Actually from the output, function starts at line 892 (index 891) and ends at line 965 (index 964)
# But the output shows line 965 is empty and 966 is the next function

new_lines = [
    b'async def validate_provenance(',
    b'    db: AsyncSession,',
    b'    context: CanonicalMutationContext,',
    b') -> bool:',
    b'    """Validate that mutation has required provenance chain and all provenance references are valid."""',
    b'    # Check required provenance based on mutation type and entity',
    b'    required_provenance = {',
    b'        "CompanyCommitment": ["authorization_id", "decision_id"],',
    b'        "CompanyAuthorization": ["decision_id", "policy_id"],',
    b'        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],',
    b'        "CompanyDecisionAlternative": ["decision_id"],',
    b'        "CompanyDecisionContradiction": ["decision_id"],',
    b'        "ObjectiveContradiction": ["objective_id"],',
    b'        }',
    b'',
    b'    required = required_provenance.get(context.target_entity_type, [])',
    b'',
    b'    for field in required:',
    b'        if not context.provenance.get(field) and not getattr(context, field, None):',
    b'            raise ProvenanceViolation(',
    b'                f"Missing required provenance: {field} for {context.target_entity_type}"',
    b'            )',
    b'',
    b'    # Validate ALL provenance references exist and belong to correct tenant',
    b'    # This applies to CREATE, UPDATE, and TRANSITION mutations',
    b'    await _validate_provenance_references(db, context)',
    b'',
    b'    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity',
    b'    # unless this is a supersession (which creates a new version with new provenance)',
    b'    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):',
    b'        # Load the existing entity to check its provenance',
    b'        entity = None',
    b'        entity_type = context.target_entity_type',
    b'        entity_id = context.target_id',
    b'       ',
    b'        if entity_type == "CompanyCommitment":',
    b'            entity = await db.get(CompanyCommitment, entity_id)',
    b'        elif entity_type == "CompanyAuthorization":',
    b'            entity = await db.get(CompanyAuthorization, entity_id)',
    b'        elif entity_type == "CompanyAction":',
    b'            entity = await db.get(CompanyAction, entity_id)',
    b'        elif entity_type == "CompanyDecisionAlternative":',
    b'            entity = await db.get(CompanyDecisionAlternative, entity_id)',
    b'        elif entity_type == "CompanyDecisionContradiction":',
    b'            entity = await db.get(CompanyDecisionContradiction, entity_id)',
    b'        elif entity_type == "ObjectiveContradiction":',
    b'            entity = await db.get(ObjectiveContradiction, entity_id)',
    b'       ',
    b'        if entity:',
    b'            # Check if this is a supersession (state transition to superseded)',
    b'            is_supersession = (',
    b'                context.mutation_type == MutationType.TRANSITION and',
    b'                context.provenance.get("state") == "superseded"',
    b'            )',
    b'           ',
    b'            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":',
    b'                # For non-supersession updates, provenance must match',
    b'            for field in required_provenance.get(context.target_entity_type, []):',
    b'                    provenance_value = context.provenance.get(field)',
    b'                    entity_value = getattr(entity, field, None)',
    b'                   ',
    b'                    if provenance_value is not None and entity_value is not None:',
    b'                        if provenance_value != entity_value:',
    b'                            raise ProvenanceViolation(',
    b'                                f"Provenance field \'{field}\' cannot be changed without supersession. "',
    b'                                f"Current value: {entity_value}, attempted: {provenance_value}. "',
    b'                                f"Use supersession to change provenance."',
    b'                            )',
    b'   ',
    b'    # Cross-tenant and cross-scope provenance validation',
    b'    # Validate for ALL mutation types that have target_id',
    b'    if context.target_id:',
    b'        await _validate_provenance_cross_boundaries(db, context)',
    b'',
    b'    return True',
]

# Read the file
with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Replace lines 891-964 (0-indexed: 891-964) with new function
# The function starts at line 892 (1-indexed) = index 891
# and ends at line 964 (1-indexed) = index 963 based on the output
# Actually from the output: starts at line 892 (index 891), ends at line 965 (index 964)
# But the output shows line 965 is empty and 966 is next function

# Let's find the exact range by looking for the function end
with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')

# Find the exact end of validate_provenance function
# It ends before "async def _validate_provenance_cross_boundaries"
start_idx = 891  # 0-indexed line where validate_provenance starts
end_idx = None
for i in range(891, len(lines)):
    if b'async def _validate_provenance_cross_boundaries' in lines[i]:
        end_idx = i
        break

print(f"validate_provenance: lines {891} to {end_idx-1} (0-indexed)")

# Now build the new file
new_lines = [
    b'async def validate_provenance(',
    b'    db: AsyncSession,',
    b'    context: CanonicalMutationContext,',
    b') -> bool:',
    b'    """Validate that mutation has required provenance chain and all provenance references are valid."""',
    b'    # Check required provenance based on mutation type and entity',
    b'    required_provenance = {',
    b'        "CompanyCommitment": ["authorization_id", "decision_id"],',
    b'        "CompanyAuthorization": ["decision_id", "policy_id"],',
    b'        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],',
    b'        "CompanyDecisionAlternative": ["decision_id"],',
    b'        "CompanyDecisionContradiction": ["decision_id"],',
    b'        "ObjectiveContradiction": ["objective_id"],',
    b'        }',
    b'',
    b'    required = required_provenance.get(context.target_entity_type, [])',
    b'',
    b'    for field in required:',
    b'        if not context.provenance.get(field) and not getattr(context, field, None):',
    b'            raise ProvenanceViolation(',
    b'                f"Missing required provenance: {field} for {context.target_entity_type}"',
    b'            )',
    b'',
    b'    # Validate ALL provenance references exist and belong to correct tenant',
    b'    # This applies to CREATE, UPDATE, and TRANSITION mutations',
    b'    await _validate_provenance_references(db, context)',
    b'',
    b'    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity',
    b'    # unless this is a supersession (which creates a new version with new provenance)',
    b'    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):',
    b'        # Load the existing entity to check its provenance',
    b'        entity = None',
    b'        entity_type = context.target_entity_type',
    b'        entity_id = context.target_id',
    b'       ',
    b'        if entity_type == "CompanyCommitment":',
    b'            entity = await db.get(CompanyCommitment, entity_id)',
    b'        elif entity_type == "CompanyAuthorization":',
    b'            entity = await db.get(CompanyAuthorization, entity_id)',
    b'        elif entity_type == "CompanyAction":',
    b'            entity = await db.get(CompanyAction, entity_id)',
    b'        elif entity_type == "CompanyDecisionAlternative":',
    b'            entity = await db.get(CompanyDecisionAlternative, entity_id)',
    b'        elif entity_type == "CompanyDecisionContradiction":',
    b'            entity = await db.get(CompanyDecisionContradiction, entity_id)',
    b'        elif entity_type == "ObjectiveContradiction":',
    b'            entity = await db.get(ObjectiveContradiction, entity_id)',
    b'       ',
    b'        if entity:',
    b'            # Check if this is a supersession (state transition to superseded)',
    b'            is_supersession = (',
    b'                context.mutation_type == MutationType.TRANSITION and',
    b'                context.provenance.get("state") == "superseded"',
    b'            )',
    b'           ',
    b'            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":',
    b'                # For non-supersession updates, provenance must match',
    b'                for field in required_provenance.get(context.target_entity_type, []):',
    b'                    provenance_value = context.provenance.get(field)',
    b'                    entity_value = getattr(entity, field, None)',
    b'                   ',
    b'                    if provenance_value is not None and entity_value is not None:',
    b'                        if provenance_value != entity_value:',
    b'                            raise ProvenanceViolation(',
    b'                                f"Provenance field \'{field}\' cannot be changed without supersession. "',
    b'                                f"Current value: {entity_value}, attempted: {provenance_value}. "',
    b'                                f"Use supersession to change provenance."',
    b'                            )',
    b'   ',
    b'    # Cross-tenant and cross-scope provenance validation',
    b'    # Validate for ALL mutation types that have target_id',
    b'    if context.target_id:',
    b'        await _validate_provenance_cross_boundaries(db, context)',
    b'',
    b'    return True',
]

# Read the file
with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')

# Find start and end of validate_provenance
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if b'async def validate_provenance(' in line:
        start_idx = i
    if start_idx is not None and end_idx is None:
        if b'async def _validate_provenance_cross_boundaries' in line:
            end_idx = i
            break

print(f"Found validate_provenance at line {start_idx+1} to {end_idx}")

# Build new content
new_lines_content = lines[:start_idx] + [
    b'async def validate_provenance(',
    b'    db: AsyncSession,',
    b'    context: CanonicalMutationContext,',
    b') -> bool:',
    b'    """Validate that mutation has required provenance chain and all provenance references are valid."""',
    b'    # Check required provenance based on mutation type and entity',
    b'    required_provenance = {',
    b'        "CompanyCommitment": ["authorization_id", "decision_id"],',
    b'        "CompanyAuthorization": ["decision_id", "policy_id"],',
    b'        "CompanyAction": ["source_commitment_id", "source_company_decision_id"],',
    b'        "CompanyDecisionAlternative": ["decision_id"],',
    b'        "CompanyDecisionContradiction": ["decision_id"],',
    b'        "ObjectiveContradiction": ["objective_id"],',
    b'        }',
    b'',
    b'    required = required_provenance.get(context.target_entity_type, [])',
    b'',
    b'    for field in required:',
    b'        if not context.provenance.get(field) and not getattr(context, field, None):',
    b'            raise ProvenanceViolation(',
    b'                f"Missing required provenance: {field} for {context.target_entity_type}"',
    b'            )',
    b'',
    b'    # Validate ALL provenance references exist and belong to correct tenant',
    b'    # This applies to CREATE, UPDATE, and TRANSITION mutations',
    b'    await _validate_provenance_references(db, context)',
    b'',
    b'    # For UPDATE/TRANSITION mutations, validate that provenance matches existing entity',
    b'    # unless this is a supersession (which creates a new version with new provenance)',
    b'    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):',
    b'        # Load the existing entity to check its provenance',
    b'        entity = None',
    b'        entity_type = context.target_entity_type',
    b'        entity_id = context.target_id',
    b'       ',
    b'        if entity_type == "CompanyCommitment":',
    b'            entity = await db.get(CompanyCommitment, entity_id)',
    b'        elif entity_type == "CompanyAuthorization":',
    b'            entity = await db.get(CompanyAuthorization, entity_id)',
    b'        elif entity_type == "CompanyAction":',
    b'            entity = await db.get(CompanyAction, entity_id)',
    b'        elif entity_type == "CompanyDecisionAlternative":',
    b'            entity = await db.get(CompanyDecisionAlternative, entity_id)',
    b'        elif entity_type == "CompanyDecisionContradiction":',
    b'            entity = await db.get(CompanyDecisionContradiction, entity_id)',
    b'        elif entity_type == "ObjectiveContradiction":',
    b'            entity = await db.get(ObjectiveContradiction, entity_id)',
    b'       ',
    b'        if entity:',
    b'            # Check if this is a supersession (state transition to superseded)',
    b'            is_supersession = (',
    b'                context.mutation_type == MutationType.TRANSITION and',
    b'                context.provenance.get("state") == "superseded"',
    b'            )',
    b'           ',
    b'            if not context.mutation_type == MutationType.TRANSITION or not context.provenance.get("state") == "superseded":',
    b'                # For non-supersession updates, provenance must match',
    b'                for field in required_provenance.get(context.target_entity_type, []):',
    b'                    provenance_value = context.provenance.get(field)',
    b'                    entity_value = getattr(entity, field, None)',
    b'                   ',
    b'                    if provenance_value is not None and entity_value is not None:',
    b'                        if provenance_value != entity_value:',
    b'                            raise ProvenanceViolation(',
    b'                                f"Provenance field \'{field}\' cannot be changed without supersession. "',
    b'                                f"Current value: {entity_value}, attempted: {provenance_value}. "',
    b'                                f"Use supersession to change provenance."',
    b'                            )',
    b'   ',
    b'    # Cross-tenant and cross-scope provenance validation',
    b'    # Validate for ALL mutation types that have target_id',
    b'    if context.target_id:',
    b'        await _validate_provenance_cross_boundaries(db, context)',
    b'',
    b'    return True',
] + [b''] + lines[end_idx:]

# Write the file
with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(b'\n'.join(new_lines))

print("Fixed validate_provenance function")
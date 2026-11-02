with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug to contradiction preservation validation
old = '''    # For UPDATE/TRANSITION of contradiction, check preservation rules
    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if not contradiction:
            return True  # Entity doesn't exist, no preservation needed

        # Check if contradiction is superseded - superseded contradictions cannot be modified
        if getattr(contradiction, "status", None) == "superseded":
            raise ContradictionPreservationViolation(
                f"Contradiction {context.target_id} is superseded and cannot be modified. "
                f"Use supersession to create a new contradiction."
            )

        # 2. Check if trying to overwrite side_a or side_b without supersession
        if context.mutation_type == MutationType.UPDATE:
            side_a = context.provenance.get("side_a_json") or context.metadata.get("side_a_json")
            side_b = context.provenance.get("side_b_json") or context.metadata.get("side_b_json")

            if side_a is not None and side_a != contradiction.side_a_json:
                # Check if trying to overwrite side_a without supersession
                raise ContradictionPreservationViolation(
                    f"Cannot modify side_a of contradiction {context.target_id} without supersession. "
                    f"Use supersession to replace a contradiction."
                )

            if side_b is not None and side_b != contradiction.side_b_json:
                raise ContradictionPreservationViolation(
                    f"Cannot modify side_b of contradiction {context.target_id} without supersession. "
                    f"Use supersession to replace a contradiction."
                )'''

new = '''    # For UPDATE/TRANSITION of contradiction, check preservation rules
    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if not contradiction:
            return True  # Entity doesn't exist, no preservation needed

        print(f"DEBUG validate_contradiction_preservation: mutation_type={context.mutation_type}, contradiction.status={getattr(contradiction, 'status', None)}, provenance={context.provenance}")

        # Check if contradiction is superseded - superseded contradictions cannot be modified
        if getattr(contradiction, "status", None) == "superseded":
            raise ContradictionPreservationViolation(
                f"Contradiction {context.target_id} is superseded and cannot be modified. "
                f"Use supersession to create a new contradiction."
            )

        # 2. Check if trying to overwrite side_a or side_b without supersession
        if context.mutation_type == MutationType.UPDATE:
            side_a = context.provenance.get("side_a_json") or context.metadata.get("side_a_json")
            side_b = context.provenance.get("side_b_json") or context.metadata.get("side_b_json")

            print(f"DEBUG validate_contradiction_preservation: side_a={side_a}, contradiction.side_a_json={contradiction.side_a_json}")

            if side_a is not None and side_a != contradiction.side_a_json:
                # Check if trying to overwrite side_a without supersession
                raise ContradictionPreservationViolation(
                    f"Cannot modify side_a of contradiction {context.target_id} without supersession. "
                    f"Use supersession to replace a contradiction."
                )

            if side_b is not None and side_b != contradiction.side_b_json:
                raise ContradictionPreservationViolation(
                    f"Cannot modify side_b of contradiction {context.target_id} without supersession. "
                    f"Use supersession to replace a contradiction."
                )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added debug to contradiction preservation validation')
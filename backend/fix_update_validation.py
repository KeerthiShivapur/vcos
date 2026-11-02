with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the contradiction preservation validation for UPDATE
old = '''    # For UPDATE/TRANSITION of contradiction, check preservation rules
    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if not contradiction:
            return True  # Entity doesn't exist, no preservation needed

        # 2. Check if trying to overwrite side_a or side_b without supersession
        if context.mutation_type == MutationType.UPDATE:
            side_a = context.provenance.get("side_a_json") or context.metadata.get("side_a_json")
            side_b = context.provenance.get("side_b_json") or context.metadata.get("side_b_json")

            if side_a is not None and side_a != getattr(context, "side_a_json", None):
                # Check if trying to overwrite side_a without supersession
                if side_a != contradiction.side_a_json:
                    raise ContradictionPreservationViolation(
                        f"Cannot modify side_a of contradiction {context.target_id} without supersession. "
                        f"Use supersession to replace a contradiction."
                    )

            if side_b is not None and side_b != getattr(context, "side_b_json", None):
                if side_b != contradiction.side_b_json:
                    raise ContradictionPreservationViolation(
                        f"Cannot modify side_b of contradiction {context.target_id} without supersession. "
                        f"Use supersession to replace a contradiction."
                    )

        # 3. Check provenance immutability
        for field in ["source_event_id", "side_a_json", "side_b_json", "lesson_memory_id", "precedent_decision_id"]:
            new_value = context.provenance.get(field) or context.metadata.get(field)
            current_value = getattr(contradiction, field, None)
            if new_value is not None and current_value is not None and new_value != current_value:
                raise ContradictionReferenceViolation(
                    f"Cannot change contradiction provenance field '{field}' without supersession. "
                    f"Current: {current_value}, attempted: {context.provenance.get(field)}"
                )'''

new = '''    # For UPDATE/TRANSITION of contradiction, check preservation rules
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
                )

        # 3. Check provenance immutability
        for field in ["source_event_id", "side_a_json", "side_b_json", "lesson_memory_id", "precedent_decision_id"]:
            new_value = context.provenance.get(field) or context.metadata.get(field)
            current_value = getattr(contradiction, field, None)
            if new_value is not None and current_value is not None and new_value != current_value:
                raise ContradictionReferenceViolation(
                    f"Cannot change contradiction provenance field '{field}' without supersession. "
                    f"Current: {current_value}, attempted: {context.provenance.get(field)}"
                )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed UPDATE validation logic and added superseded check')
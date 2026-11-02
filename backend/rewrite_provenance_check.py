with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the provenance check section and replace it completely
new_lines = []
i = 0
while i < len(lines):
    if i < len(lines) and '# 4. PROVENANCE PRESERVATION DURING EPISTEMIC TRANSITION' in lines[i]:
        # Skip the old provenance check section
        new_lines.append(lines[i])  # # 4. PROVENANCE...
        new_lines.append(lines[i+1])  # =====...
        new_lines.append(lines[i+2])  # # If this is an UPDATE...
        new_lines.append(lines[i+3])  # if context.target_id...
        new_lines.append(lines[i+4])  #     # Load existing...
        new_lines.append(lines[i+5])  #         from app.models...
        new_lines.append(lines[i+6])  #         from app.models...
        new_lines.append(lines[i+7])  #         from app.models...
        new_lines.append(lines[i+8])  #         entity_type_map = {
        new_lines.append(lines[i+9])  #             "CompanyDecision": ...
        new_lines.append(lines[i+10])  #             "CompanyCommitment": ...
        new_lines.append(lines[i+11])  #             "CompanyAuthorization": ...
        new_lines.append(lines[i+12])  #             "CompanyAction": ...
        new_lines.append(lines[i+13])  #         }
        new_lines.append(lines[i+14])  #         model = ...
        new_lines.append(lines[i+15])  #         if model:
        new_lines.append(lines[i+16])  #             existing = await db.get...
        new_lines.append(lines[i+17])  #             if existing:
        new_lines.append('                # DEBUG\n')
        new_lines.append('                print(f"DEBUG provenance check: existing.provenance={getattr(existing, \'provenance\', None)}, new_provenance={context.provenance}")\n')
        new_lines.append('                # Check if provenance is being stripped\n')
        new_lines.append('                existing_provenance = getattr(existing, "provenance", None)\n')
        new_lines.append('                new_provenance = context.provenance or {}\n')
        new_lines.append('\n')
        new_lines.append('                # If existing entity has provenance, new provenance must not strip it\n')
        new_lines.append('                if existing_provenance:\n')
        new_lines.append('                    # Verify critical provenance fields are not stripped\n')
        new_lines.append('                    critical_fields = ["source_event_id", "decision_id", "authorization_id", "commitment_id", "evidence_ids"]\n')
        new_lines.append('                    for field in critical_fields:\n')
        new_lines.append('                        if existing_provenance.get(field) and not new_provenance.get(field):\n')
        new_lines.append('                            raise ProvenanceStrippingViolation(\n')
        new_lines.append('                                f"Epistemic transition cannot strip provenance field \'{field}\'. "\n')
        new_lines.append('                                f"Original: {existing_provenance.get(field)}"\n')
        new_lines.append('                            )\n')
        new_lines.append('                    # Also check if new provenance is empty - any UPDATE must preserve provenance\n')
        new_lines.append('                    if not new_provenance:\n')
        new_lines.append('                        raise ProvenanceStrippingViolation(\n')
        new_lines.append('                            f"Epistemic transition cannot strip all provenance. "\n')
        new_lines.append('                            f"Original provenance had: {list(existing_provenance.keys())}"\n')
        new_lines.append('                        )\n')
        new_lines.append('                # If no existing provenance but promoting to strong status, require provenance\n')
        new_lines.append('                elif not new_provenance and context.epistemic_status in (\n')
        new_lines.append('                    EpistemicStatus.OBSERVED, EpistemicStatus.MEASURED, EpistemicStatus.EVIDENCE_BACKED\n')
        new_lines.append('                ):\n')
        new_lines.append('                    raise ProvenanceStrippingViolation(\n')
        new_lines.append('                        f"Promotion to {context.epistemic_status} requires provenance to be provided"\n')
        new_lines.append('                    )\n')
        
        # Skip the old provenance check lines until we hit the next section
        i += 18  # Skip past the old provenance check
        while i < len(lines) and '# ================================================================' not in lines[i] or '5. HISTORICAL' not in lines[i]:
            if '# ================================================================' in lines[i] and '5. HISTORICAL' in lines[i+1] if i+1 < len(lines) else False:
                break
            i += 1
        continue
    else:
        new_lines.append(lines[i])
        i += 1

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Rewrote provenance check section completely')
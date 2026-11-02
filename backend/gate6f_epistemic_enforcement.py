with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# First, let's add new exception classes for epistemic violations
old_exceptions = '''class EpistemicViolation(CanonicalMutationError):
    """Mutation violates epistemic boundary rules."""
    pass


class ContradictionViolation(CanonicalMutationError):
    """Mutation violates contradiction preservation rules."""
    pass


class ContradictionPreservationViolation(CanonicalMutationError):
    """Mutation violates contradiction preservation (Gate 6-E)."""
    pass


class ContradictionReferenceViolation(CanonicalMutationError):
    """Mutation violates contradiction reference integrity."""
    pass'''

new_exceptions = '''class EpistemicViolation(CanonicalMutationError):
    """Mutation violates epistemic boundary rules."""
    pass


class EpistemicPromotionViolation(CanonicalMutationError):
    """Mutation attempts invalid epistemic promotion without required evidence."""
    pass


class EpistemicDemotionViolation(CanonicalMutationError):
    """Mutation attempts to downgrade epistemic status destroying historical meaning."""
    pass


class AIOriginViolation(CanonicalMutationError):
    """AI-generated content attempted to become canonical fact without explicit marking."""
    pass


class EvidenceTruthConfusionViolation(CanonicalMutationError):
    """Mutation conflates evidence with verified truth."""
    pass


class ProvenanceStrippingViolation(CanonicalMutationError):
    """Mutation strips provenance during epistemic transition."""
    pass


class ContradictionViolation(CanonicalMutationError):
    """Mutation violates contradiction preservation rules."""
    pass


class ContradictionPreservationViolation(CanonicalMutationError):
    """Mutation violates contradiction preservation (Gate 6-E)."""
    pass


class ContradictionReferenceViolation(CanonicalMutationError):
    """Mutation violates contradiction reference integrity."""
    pass'''

content = content.replace(old_exceptions, new_exceptions)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added new exception classes')
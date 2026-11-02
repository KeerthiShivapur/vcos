with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add new exception classes after EpistemicViolation
old_exceptions = '''class EpistemicViolation(CanonicalMutationError):
    """Mutation violates epistemic boundaries."""
    pass


class ConcurrencyViolation(CanonicalMutationError):'''

new_exceptions = '''class EpistemicViolation(CanonicalMutationError):
    """Mutation violates epistemic boundaries."""
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


class ConcurrencyViolation(CanonicalMutationError):'''

content = content.replace(old_exceptions, new_exceptions)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added new exception classes')
"""Tests for Deterministic Semantic Sampling."""

import pytest
from tests.scale.semantic_sampling import (
    DeterministicSampler,
    SampleSpec,
    SamplingStrategy,
    SemanticSampleResult,
)


class TestDeterministicSampler:
    
    def test_uniform_sampling_deterministic(self):
        sampler = DeterministicSampler(base_seed=42)
        
        population = list(range(100))
        
        spec1 = SampleSpec(
            entity_type="test",
            sample_size=10,
            strategy=SamplingStrategy.DETERMINISTIC_UNIFORM,
            seed=42,
        )
        
        spec2 = SampleSpec(
            entity_type="test",
            sample_size=10,
            strategy=SamplingStrategy.DETERMINISTIC_UNIFORM,
            seed=42,
        )
        
        sample1 = sampler.sample_uniform(population, spec1, id_extractor=lambda x: str(x))
        sample2 = sampler.sample_uniform(population, spec2, id_extractor=lambda x: str(x))
        
        assert sample1 == sample2
        assert len(sample1) == 10
    
    def test_different_seeds_different_samples(self):
        sampler = DeterministicSampler(base_seed=42)
        
        population = list(range(100))
        
        spec1 = SampleSpec(
            entity_type="test",
            sample_size=10,
            strategy=SamplingStrategy.DETERMINISTIC_UNIFORM,
            seed=42,
        )
        
        spec2 = SampleSpec(
            entity_type="test",
            sample_size=10,
            strategy=SamplingStrategy.DETERMINISTIC_UNIFORM,
            seed=43,
        )
        
        sample1 = sampler.sample_uniform(population, spec1, id_extractor=lambda x: str(x))
        sample2 = sampler.sample_uniform(population, spec2, id_extractor=lambda x: str(x))
        
        assert sample1 != sample2
    
    def test_stratified_sampling(self):
        sampler = DeterministicSampler(base_seed=42)
        
        # Create population with strata
        population = []
        for stratum in ["A", "B", "C"]:
            for i in range(10):
                population.append({"id": f"{stratum}{i}", "stratum": stratum})
        
        spec = SampleSpec(
            entity_type="test",
            sample_size=15,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=42,
        )
        
        sampled = sampler.sample_stratified(
            population,
            spec,
            id_extractor=lambda x: x["id"],
            stratum_extractor=lambda x: x["stratum"],
        )
        
        assert len(sampled) == 15
        
        # Check all strata represented
        strata_found = set()
        for item in population:
            if item["id"] in sampled:
                strata_found.add(item["stratum"])
        
        assert len(strata_found) >= 2  # At least some strata represented
    
    def test_stratified_sampling_deterministic(self):
        sampler = DeterministicSampler(base_seed=42)
        
        population = []
        for stratum in ["A", "B", "C"]:
            for i in range(10):
                population.append({"id": f"{stratum}{i}", "stratum": stratum})
        
        spec1 = SampleSpec(
            entity_type="test",
            sample_size=15,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=42,
        )
        
        spec2 = SampleSpec(
            entity_type="test",
            sample_size=15,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=42,
        )
        
        sample1 = sampler.sample_stratified(
            population, spec1,
            id_extractor=lambda x: x["id"],
            stratum_extractor=lambda x: x["stratum"],
        )
        
        sample2 = sampler.sample_stratified(
            population, spec2,
            id_extractor=lambda x: x["id"],
            stratum_extractor=lambda x: x["stratum"],
        )
        
        assert sample1 == sample2
    
    def test_sample_spec_hash_deterministic(self):
        spec1 = SampleSpec(
            entity_type="employee",
            sample_size=100,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=42,
            filters={"status": "active"},
        )
        
        spec2 = SampleSpec(
            entity_type="employee",
            sample_size=100,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=42,
            filters={"status": "active"},
        )
        
        assert spec1.get_hash() == spec2.get_hash()
    
    def test_sample_spec_hash_different_inputs(self):
        spec1 = SampleSpec(
            entity_type="employee",
            sample_size=100,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=42,
        )
        
        spec2 = SampleSpec(
            entity_type="employee",
            sample_size=100,
            strategy=SamplingStrategy.STRATIFIED_BY_DEPARTMENT,
            seed=43,
        )
        
        assert spec1.get_hash() != spec2.get_hash()


class TestSemanticSampleResult:
    
    def test_result_serialization(self):
        spec = SampleSpec(
            entity_type="employee",
            sample_size=100,
            strategy=SamplingStrategy.DETERMINISTIC_UNIFORM,
            seed=42,
        )
        
        result = SemanticSampleResult(
            spec=spec,
            sampled_ids=["emp_1", "emp_2", "emp_3"],
            total_population=1000,
            validation_checks={"has_email": True, "valid_status": True},
            anomalies=[],
            passed=True,
        )
        
        data = result.to_dict()
        
        assert data["spec"]["entity_type"] == "employee"
        assert data["sampled_ids"] == ["emp_1", "emp_2", "emp_3"]
        assert data["total_population"] == 1000
        assert data["passed"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
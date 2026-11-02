import re

with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Remove duplicate COMPLETED transition
content = content.replace(
    '        self._state_machine.transition(ScaleRunState.COMPLETED)\n\n    # ================================================================\n    # PIPELINE PHASES\n    # ================================================================\n\n    self._state_machine.transition(ScaleRunState.COMPLETED)\n\n    async def _phase_cleanup_existing_data(self):',
    '        self._state_machine.transition(ScaleRunState.COMPLETED)\n\n    # ================================================================\n    # PIPELINE PHASES\n    # ================================================================\n\n    async def _phase_environment_preflight(self):'
)

# Fix 2: Fix the _phase_generation method - replace the entire method
# We'll use regex to find and replace the method
import re

old_gen_pattern = r'(    async def _phase_generation\(self\):.*?)(?=\n    async def _phase_|\nclass |\Z)'

def new_gen(match):
    return '''    async def _phase_generation(self):
        """Phase 3: Scale dataset generation with checkpointing."""
        self._state_machine.advance_phase(ScaleRunPhase.GENERATION)
        self._state_machine.transition(ScaleRunState.GENERATING)

        try:
            print("DEBUG: Starting generation phase...", flush=True)
            # Create organization for this scale run
            with self.environment.sync_session() as sync_db:
                org = Organization(
                    id=uuid.uuid4().hex[:32],
                    name=f"Scale Test {self.profile.name} ({self.profile.employee_count} employees)",
                    slug=f"scale-{self.profile.name}-{uuid.uuid4().hex[:8]}",
                    industry="Technology",
                    country="US",
                    timezone="UTC",
                    currency="USD",
                    language="en",
                    status="active",
                )
                sync_db.add(org)
                sync_db.flush()
                org_id = org.id
                print(f"DEBUG: Created org {org_id}", flush=True)
                
                # Run generation
                profile = UNIVERSAL_SCALE_PROFILES.get(self.profile.name)
                if not profile:
                    profile = UniversalScaleProfile(name=self.profile.name, employee_count=self.profile.employee_count)
                
                generator = SyncScaleGenerator(
                    sync_db, org_id, self.profile,
                    run_metadata=self._run_metadata,
                    state_store=self._state_store,
                )
                
                print("DEBUG: Starting generator.generate_all()", flush=True)
                start = time.perf_counter()
                counts = generator.generate_all()
                generation_time = time.perf_counter() - start
                print(f"DEBUG: Generation completed in {generation_time:.2f}s", flush=True)
                
                total_rows = sum(counts.values())
                throughput = total_rows / generation_time if generation_time > 0 else 0
                
                # Store generation evidence
                self._evidence.generation = GenerationEvidence(
                    entities_generated=counts,
                    total_rows=total_rows,
                    generation_duration_seconds=generation_time,
                    throughput_rows_per_second=throughput,
                    checkpoint_completion={k: True for k in counts.keys()},
                    retry_count=self._run_metadata.retry_count if self._run_metadata else 0,
                )
                
                # Store counts for later phases
                self.results = counts
                self.org_id = org_id
                
                self._evidence.set_mandatory_check("generation_complete", True)
                self._state_machine.transition(ScaleRunState.DATA_GENERATED)
                print("DEBUG: Generation phase completed successfully", flush=True)
                
        except Exception as e:
            print(f"DEBUG: Generation failed with error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self._evidence.set_mandatory_check("generation_complete", False)
            self._state_machine.transition(ScaleRunState.FAILED, str(e))
            raise

# Use regex to replace the method
pattern = r'(    async def _phase_generation\(self\):.*?)(?=\n    async def _phase_|\nclass |\Z)'
content = re.sub(pattern, new_gen, content, flags=re.DOTALL)

with open(r'D:\vcos1\workspace\vcos\backend\tests\scale\postgres\scale_runner.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed generation method')

with open(r'D:\vcos1\workspace\vcos\backend\fix_scale_runner_final.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed')
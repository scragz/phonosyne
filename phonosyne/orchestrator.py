"""
Orchestrator for the Phonosyne Pipeline

This module defines the `Manager` class, which orchestrates the entire
Phonosyne sound generation pipeline from user brief to a collection of WAV files.

Key features:
- Initializes and uses Designer, Analyzer, and Compiler agents.
- Manages the overall workflow:
  1. DesignerAgent: User brief -> Design plan (list of sample stubs).
  2. For each sample stub (concurrently using ProcessPoolExecutor):
     a. AnalyzerAgent: Sample stub -> Detailed synthesis recipe (AnalyzerOutput).
     b. CompilerAgent: Synthesis recipe -> Python DSP code -> Executes code -> WAV file.
     c. Validator: Validates the generated WAV file.
- Handles concurrency for processing multiple samples in parallel.
- Collects results, logs progress, and writes a final manifest.json.

@dependencies
- `concurrent.futures.ProcessPoolExecutor` for parallelism.
- `pathlib.Path` for file system operations.
- `logging` for detailed logging.
- `json` for writing the manifest file.
- `phonosyne.settings` for configuration (e.g., default workers, output directory).
- `phonosyne.agents` (DesignerAgent, AnalyzerAgent, CompilerAgent, and their schemas).
- `phonosyne.dsp.validators.validate_wav` and `ValidationFailedError`.
- `phonosyne.utils.slugify` for creating output directory names.
- `tqdm` for progress bars (optional).

@notes
- Error handling and retry logic at the orchestrator level (e.g., for a whole sample failing)
  will be important. Agents have their own internal retries for LLM calls.
- The manifest.json will summarize the generated collection.
"""

import concurrent.futures
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel  # Moved import to top
from tqdm import tqdm

from phonosyne import settings
from phonosyne.agents import SampleStub  # Individual sample from Designer's plan
from phonosyne.agents import (
    AnalyzerAgent,
    AnalyzerInput,
)
from phonosyne.agents import (
    AnalyzerOutput as CompilerInput,  # AnalyzerOutput is input to Compiler
)
from phonosyne.agents import (
    CompilerAgent,
    DesignerAgent,
    DesignerAgentInput,
)
from phonosyne.agents import (
    DesignerOutput as DesignPlanSchema,  # Full plan from Designer
)
from phonosyne.dsp.validators import ValidationFailedError, validate_wav
from phonosyne.utils import slugify

logger = logging.getLogger(__name__)


class SampleGenerationResult(BaseModel):  # Requires pydantic import
    """Pydantic model to store result of a single sample generation task."""

    sample_id: str
    status: (
        str  # "success", "failed_analysis", "failed_compilation", "failed_validation"
    )
    output_path: Optional[Path] = None
    error_message: Optional[str] = None
    attempts: Optional[int] = None  # e.g. compiler attempts

    class Config:
        arbitrary_types_allowed = True


class Manager:
    """
    Orchestrates the Phonosyne sound generation pipeline.
    """

    def __init__(self, num_workers: Optional[int] = None, verbose: bool = False):
        self.num_workers = (
            num_workers if num_workers is not None else settings.DEFAULT_WORKERS
        )
        if self.num_workers == 0:  # 0 means serial execution
            self.num_workers = 1
            logger.info("Running in serial mode (1 worker).")
        else:
            logger.info(f"Initializing Manager with {self.num_workers} worker(s).")

        self.verbose = verbose  # Controls verbosity of logging / tqdm

        self.designer_agent = DesignerAgent()
        self.analyzer_agent = AnalyzerAgent()
        self.compiler_agent = CompilerAgent()

        self.output_base_dir = settings.DEFAULT_OUT_DIR
        self.output_base_dir.mkdir(parents=True, exist_ok=True)

    def _process_single_sample(
        self, sample_stub: SampleStub, design_plan_slug: str, run_output_dir: Path
    ) -> SampleGenerationResult:
        """
        Processes a single sample stub through Analyzer, Compiler, and Validator.
        This method is designed to be run in a separate process by ProcessPoolExecutor.
        """
        sample_id = sample_stub.id
        logger.info(f"[Sample: {sample_id}] Starting processing.")

        try:
            # 1. AnalyzerAgent
            logger.debug(f"[Sample: {sample_id}] Running AnalyzerAgent...")
            analyzer_input = AnalyzerInput(
                id=sample_id,
                seed_description=sample_stub.seed_description,
                duration_s=sample_stub.duration_s,
            )
            synthesis_recipe: CompilerInput = self.analyzer_agent.process(
                analyzer_input.model_dump()
            )
            logger.info(
                f"[Sample: {sample_id}] AnalyzerAgent completed. Effect name: {synthesis_recipe.effect_name}"
            )

            # 2. CompilerAgent
            # The CompilerAgent's run method needs the validator_fn.
            # The actual output path for the WAV will be determined by CompilerAgent/exec_env
            # and then potentially moved/renamed by the orchestrator.
            # For now, CompilerAgent returns a path to a validated WAV in a persistent temp location.

            # The final filename for this sample in the run_output_dir
            final_sample_filename = (
                f"{sample_id}_{slugify(synthesis_recipe.effect_name)}.wav"
            )
            # Note: CompilerAgent's output_filename in run_code is for its *internal* temp file.
            # The path returned by compiler_agent.run() is the one we care about.

            logger.debug(
                f"[Sample: {sample_id}] Running CompilerAgent for '{synthesis_recipe.effect_name}'..."
            )

            # Pass the validator function to the compiler agent's run method
            # The CompilerAgent's `run` method expects `inputs: AnalyzerOutput`
            # and `**kwargs` which can include `validator_fn`.
            # The `process` method of AgentBase handles input schema validation.
            # We call `run` directly here as we already have the validated `synthesis_recipe`.

            # The validator needs the `AnalyzerOutput` (synthesis_recipe) for spec.
            validator_partial = lambda path: validate_wav(path, synthesis_recipe)

            temp_wav_path: Path = self.compiler_agent.run(
                inputs=synthesis_recipe,
                validator_fn=validator_partial,  # Pass our validator
            )
            logger.info(
                f"[Sample: {sample_id}] CompilerAgent completed. Temporary WAV at: {temp_wav_path}"
            )

            # Move the validated WAV from its persistent temporary location to the final run output directory
            final_wav_path = run_output_dir / final_sample_filename
            try:
                shutil.move(str(temp_wav_path), final_wav_path)
                logger.info(
                    f"[Sample: {sample_id}] Moved validated WAV to final location: {final_wav_path}"
                )
            except Exception as e_move:
                logger.error(
                    f"[Sample: {sample_id}] Failed to move WAV from {temp_wav_path} to {final_wav_path}: {e_move}"
                )
                # If move fails, try to copy and then delete source, or just report error.
                # For now, consider it a failure for this sample.
                return SampleGenerationResult(
                    sample_id=sample_id,
                    status="failed_file_operation",
                    error_message=f"Failed to move WAV: {e_move}",
                )
            finally:
                # Clean up the source temp file if it still exists (e.g. if move failed but we copied)
                # shutil.move should remove source, but defensive cleanup.
                if temp_wav_path.exists():
                    try:
                        temp_wav_path.unlink()
                    except OSError:
                        logger.warning(
                            f"[Sample: {sample_id}] Could not clean up temp WAV: {temp_wav_path}"
                        )

            return SampleGenerationResult(
                sample_id=sample_id, status="success", output_path=final_wav_path
            )

        except ValidationFailedError as e_val:
            logger.error(f"[Sample: {sample_id}] Validation failed: {e_val}")
            return SampleGenerationResult(
                sample_id=sample_id,
                status="failed_validation",
                error_message=str(e_val),
            )
        except Exception as e:  # Catch errors from Analyzer or Compiler agents
            logger.error(
                f"[Sample: {sample_id}] Processing failed: {type(e).__name__}: {e}",
                exc_info=self.verbose,
            )
            # Determine if it was analysis or compilation stage if possible, for better status
            # This generic catch might obscure the stage.
            # For now, assume compilation if recipe was obtained.
            status = (
                "failed_analysis"
                if "synthesis_recipe" not in locals()
                else "failed_compilation"
            )
            return SampleGenerationResult(
                sample_id=sample_id, status=status, error_message=str(e)
            )

    def run(self, user_brief: str) -> Dict[str, Any]:
        """
        Runs the full Phonosyne pipeline for a given user brief.

        Args:
            user_brief: The natural-language sound design brief from the user.

        Returns:
            A dictionary summarizing the outcome, including status, number of
            rendered files, and output directory path.
        """
        start_time = time.time()
        logger.info(f"Phonosyne pipeline started for brief: '{user_brief[:100]}...'")

        # 1. Call DesignerAgent to get the design plan
        try:
            logger.info("Running DesignerAgent...")
            designer_input = DesignerAgentInput(user_brief=user_brief)
            design_plan: DesignPlanSchema = self.designer_agent.process(
                designer_input.model_dump()
            )
            logger.info(
                f"DesignerAgent completed. Plan slug: {design_plan.brief_slug}, Movements: {len(design_plan.movements)}"
            )
        except Exception as e:
            logger.error(f"DesignerAgent failed: {e}", exc_info=self.verbose)
            return {
                "status": "error",
                "reason": f"DesignerAgent failed: {e}",
                "rendered": 0,
                "output_dir": None,
            }

        # Prepare output directory for this run
        run_output_dir_name = slugify(
            f"{time.strftime('%Y%m%d-%H%M%S')}_{design_plan.brief_slug}"
        )
        run_output_dir = self.output_base_dir / run_output_dir_name
        run_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory for this run: {run_output_dir}")

        all_sample_stubs: List[SampleStub] = []
        for movement in design_plan.movements:
            all_sample_stubs.extend(movement.samples)

        num_total_samples = len(all_sample_stubs)
        logger.info(f"Total samples to generate: {num_total_samples}")

        results: List[SampleGenerationResult] = []

        # 2. Process each sample stub (concurrently or serially)
        # Use ProcessPoolExecutor for true parallelism if num_workers > 1
        # Note: Agent instances (self.analyzer_agent, self.compiler_agent) are not directly
        # picklable for ProcessPoolExecutor if they contain unpicklable state (like HTTP clients).
        # AgentBase initializes its OpenAI client in __init__.
        # This means _process_single_sample needs to instantiate its own agents,
        # or we need to ensure agents are picklable / use a different concurrency model.

        # For ProcessPoolExecutor, the target function `_process_single_sample`
        # cannot be a method of `self` if `self` (Manager instance) is not picklable
        # due to containing agent instances with HTTP clients.
        # A common pattern is to make the worker function a static method or top-level function,
        # passing all necessary data.

        # Simpler approach for now: if num_workers > 1, it implies agents might need to be
        # re-initialized in the worker or made picklable.
        # Let's assume for now that the agents are sufficiently picklable or that
        # the overhead of re-init is acceptable for the number of tasks.
        # If not, `_process_single_sample` would need to become a staticmethod or top-level
        # function that re-creates agents.

        # Given AgentBase initializes OpenAI client, it's not picklable.
        # So, _process_single_sample must be a static method or top-level,
        # and it must create its own agent instances.
        # This means we can't use self.analyzer_agent etc. inside it.
        # This is a significant refactor of _process_single_sample.

        # Let's adjust _process_single_sample to be a static method.
        # This means it won't have access to self.analyzer_agent etc.
        # It will need to instantiate them.

        # For now, to keep moving, I'll assume serial execution or ThreadPoolExecutor
        # if agents are not picklable. True CPU-bound parallelism for LLM calls (which are I/O bound)
        # and DSP code (CPU bound) is tricky.
        # If num_workers is for parallel LLM calls, ThreadPoolExecutor is fine.
        # If it's for parallel DSP code execution (via LocalPythonExecutor), ProcessPoolExecutor is better.
        # LocalPythonExecutor itself is CPU bound.

        # Let's use ThreadPoolExecutor for now, as LLM calls are I/O bound.
        # This avoids pickling issues with agent instances.
        # If DSP becomes a bottleneck, might need a hybrid approach or make agents picklable.

        executor_class = (
            concurrent.futures.ThreadPoolExecutor if self.num_workers > 1 else None
        )

        if executor_class:
            with executor_class(max_workers=self.num_workers) as executor:
                futures_map = {
                    executor.submit(
                        Manager._static_process_single_sample,
                        stub,
                        design_plan.brief_slug,
                        run_output_dir,
                        self.verbose,
                    ): stub
                    for stub in all_sample_stubs
                }

                # Setup tqdm progress bar if not verbose (verbose might have its own detailed logs)
                progress_bar = tqdm(
                    concurrent.futures.as_completed(futures_map),
                    total=num_total_samples,
                    desc="Processing samples",
                    disable=self.verbose,  # Disable tqdm if verbose logging is on
                )
                for future in progress_bar:
                    sample_stub = futures_map[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(
                            f"Error processing sample {sample_stub.id}: {e}",
                            exc_info=self.verbose,
                        )
                        results.append(
                            SampleGenerationResult(
                                sample_id=sample_stub.id,
                                status="failed_orchestration",
                                error_message=str(e),
                            )
                        )
                    progress_bar.set_postfix_str(
                        f"Last: {sample_stub.id} {results[-1].status if results else ''}"
                    )
        else:  # Serial execution
            logger.info("Processing samples serially...")
            for stub in tqdm(
                all_sample_stubs,
                desc="Processing samples serially",
                disable=self.verbose,
            ):
                try:
                    result = Manager._static_process_single_sample(
                        stub, design_plan.brief_slug, run_output_dir, self.verbose
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(
                        f"Error processing sample {stub.id}: {e}", exc_info=self.verbose
                    )
                    results.append(
                        SampleGenerationResult(
                            sample_id=stub.id,
                            status="failed_orchestration",
                            error_message=str(e),
                        )
                    )

        # 3. Collect results and write manifest
        successful_samples = [res for res in results if res.status == "success"]
        failed_samples_count = num_total_samples - len(successful_samples)

        manifest_data = {
            "user_brief": user_brief,
            "brief_slug": design_plan.brief_slug,
            "output_directory": str(
                run_output_dir.relative_to(Path.cwd())
            ),  # Relative path
            "total_samples_planned": num_total_samples,
            "total_samples_succeeded": len(successful_samples),
            "total_samples_failed": failed_samples_count,
            "generation_time_seconds": time.time() - start_time,
            "movements": design_plan.model_dump()[
                "movements"
            ],  # Include original plan structure
            "sample_results": [
                res.model_dump(exclude_none=True, mode="json") for res in results
            ],  # Store serializable results
        }

        manifest_path = run_output_dir / "manifest.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)
            logger.info(f"Manifest file written to: {manifest_path}")
        except Exception as e:
            logger.error(f"Failed to write manifest.json: {e}")

        final_status = (
            "success"
            if failed_samples_count == 0
            else "partial_success" if successful_samples else "error"
        )
        logger.info(
            f"Phonosyne pipeline finished. Status: {final_status}. {len(successful_samples)}/{num_total_samples} samples generated."
        )

        return {
            "status": final_status,
            "rendered": len(successful_samples),
            "total_planned": num_total_samples,
            "output_dir": str(run_output_dir),
        }

    @staticmethod
    def _static_process_single_sample(
        sample_stub: SampleStub,
        design_plan_slug: str,
        run_output_dir: Path,
        verbose_logging: bool,
    ) -> SampleGenerationResult:
        """
        Static method to process a single sample. Instantiates its own agents.
        This is suitable for use with ProcessPoolExecutor.
        """
        # Re-initialize agents here as they are not picklable.
        # This adds overhead but allows true multiprocessing if LocalPythonExecutor is CPU bound.
        # If LLM calls are the main bottleneck, ThreadPoolExecutor with shared agents is fine.
        # Current implementation uses ThreadPoolExecutor, so this static method is called
        # but could also be an instance method if agents were made picklable or if we ensure
        # that the state within agents (like OpenAI client) is handled correctly across threads.
        # For simplicity and to match the structure for potential ProcessPool use:
        analyzer = AnalyzerAgent()
        compiler = CompilerAgent()
        # No need for DesignerAgent here.

        sample_id = sample_stub.id
        # Configure logger for this process/thread if needed, or rely on root logger propagation.
        # logger_sps = logging.getLogger(f"{__name__}.sample_worker.{sample_id}") # Example specific logger
        # logger_sps.info(f"Starting processing.") # Use this logger_sps instead of global logger

        # Using global logger for now, assuming it's thread-safe or configured for multiprocessing.
        logger.info(f"[SampleProc: {sample_id}] Starting processing.")

        try:
            logger.debug(f"[SampleProc: {sample_id}] Running AnalyzerAgent...")
            analyzer_input_data = AnalyzerInput(
                id=sample_id,
                seed_description=sample_stub.seed_description,
                duration_s=sample_stub.duration_s,
            )
            synthesis_recipe: CompilerInput = analyzer.process(
                analyzer_input_data.model_dump()
            )
            logger.info(
                f"[SampleProc: {sample_id}] AnalyzerAgent completed. Effect: {synthesis_recipe.effect_name}"
            )

            final_sample_filename = (
                f"{sample_id}_{slugify(synthesis_recipe.effect_name)}.wav"
            )
            logger.debug(
                f"[SampleProc: {sample_id}] Running CompilerAgent for '{synthesis_recipe.effect_name}'..."
            )

            validator_partial = lambda path: validate_wav(path, synthesis_recipe)

            temp_wav_path: Path = compiler.run(
                inputs=synthesis_recipe, validator_fn=validator_partial
            )
            logger.info(
                f"[SampleProc: {sample_id}] CompilerAgent completed. Temp WAV: {temp_wav_path}"
            )

            final_wav_path = run_output_dir / final_sample_filename
            try:
                # Ensure parent directory of final_wav_path exists, though run_output_dir should already.
                final_wav_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(temp_wav_path), final_wav_path)
                logger.info(f"[SampleProc: {sample_id}] Moved WAV to: {final_wav_path}")
            except Exception as e_move:
                logger.error(
                    f"[SampleProc: {sample_id}] Failed to move WAV from {temp_wav_path} to {final_wav_path}: {e_move}"
                )
                if temp_wav_path.exists():
                    temp_wav_path.unlink(missing_ok=True)  # cleanup temp if move failed
                return SampleGenerationResult(
                    sample_id=sample_id,
                    status="failed_file_operation",
                    error_message=f"Move failed: {e_move}",
                )

            # Defensive cleanup of source temp file if shutil.move didn't remove it (it should)
            if temp_wav_path.exists():
                temp_wav_path.unlink(missing_ok=True)

            return SampleGenerationResult(
                sample_id=sample_id, status="success", output_path=final_wav_path
            )

        except ValidationFailedError as e_val:
            logger.error(f"[SampleProc: {sample_id}] Validation failed: {e_val}")
            return SampleGenerationResult(
                sample_id=sample_id,
                status="failed_validation",
                error_message=str(e_val),
            )
        except Exception as e:
            logger.error(
                f"[SampleProc: {sample_id}] Processing failed: {type(e).__name__}: {e}",
                exc_info=verbose_logging,
            )
            status = (
                "failed_analysis"
                if "synthesis_recipe" not in locals()
                else "failed_compilation"
            )
            return SampleGenerationResult(
                sample_id=sample_id, status=status, error_message=str(e)
            )


if __name__ == "__main__":
    # Basic configuration for standalone testing
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if not settings.OPENROUTER_API_KEY:
        print("Skipping Manager test: OPENROUTER_API_KEY not set in .env")
    else:
        print("Testing Manager (will make real LLM calls and execute code)...")
        # Test with a small number of workers for this example
        manager = Manager(num_workers=2, verbose=True)

        test_brief = "A short set of three glitchy, robotic sound effects for a UI."
        # To make this test faster, we might want to mock the DesignerAgent
        # to return a plan with only 1-2 samples.
        # For now, it will try to generate the full 18 if the LLM complies.

        # Monkeypatch DesignerAgent for a quicker test if needed:
        # class MockDesignerAgent(DesignerAgent):
        #     def process(self, raw_inputs: Dict[str, Any], **kwargs: Any) -> DesignPlanSchema:
        #         logger.info("Using MOCKED DesignerAgent process method.")
        #         return DesignPlanSchema(
        #             brief_slug="mocked-glitchy-ui",
        #             movements=[
        #                 MovementStub(id="movement_1", name="Mock Movement", samples=[
        #                     SampleStub(id="S1.1", seed_description="A short clicky glitch", duration_s=0.5),
        #                     SampleStub(id="S1.2", seed_description="A robotic whir", duration_s=1.0),
        #                 ])
        #             ]
        #         )
        # manager.designer_agent = MockDesignerAgent()
        # logger.info("Patched manager.designer_agent with MockDesignerAgent for test.")

        try:
            result_summary = manager.run(user_brief=test_brief)
            print("\nManager Run Summary:")
            print(
                json.dumps(result_summary, indent=2, default=str)
            )  # Use default=str for Path objects

            print(f"\nCheck the output directory: {result_summary.get('output_dir')}")
            if result_summary.get("status") != "success":
                print(
                    "Pipeline did not complete successfully for all samples. Check logs and manifest.json."
                )

        except Exception as e:
            print(
                f"\nAn critical error occurred during Manager test: {e}", exc_info=True
            )

# Need to import BaseModel for SampleGenerationResult
# from pydantic import BaseModel # Commented out / removed from bottom

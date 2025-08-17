import asyncio
import os
import shutil
import tempfile
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy.orm import Session

from app.crud import crud_submission
from app.db.session import SessionLocal
from app.sandbox.common import diff_files
from app.sandbox.engine import run_sandboxed
from app.schemas.problem import Problem, TestCase
from app.schemas.submission import SubmissionStatus, TestCaseResult
from app.services.contest_service import get_problem_by_id

MAX_THREADS = (os.cpu_count() or 2) * 2
blocking_executor = ThreadPoolExecutor(max_workers=MAX_THREADS)


async def _judge_test_case(
        submission_id: uuid.UUID,
        code: str,
        language: str,
        problem: Problem,
        test_case: TestCase
) -> TestCaseResult:
    user_run_result = await run_sandboxed(
        code=code,
        language=language,
        run_input=test_case.input_content,
        time_limit_sec=problem.time_limit_sec,
        memory_limit_mb=problem.memory_limit_mb,
        unit_name_prefix=f"sub-{submission_id.hex[:8]}"
    )

    if user_run_result.status == 'compilation_error':
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.COMPILATION_ERROR,
                              stderr=user_run_result.compilation_stderr)

    if user_run_result.status == 'timeout':
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.TIME_LIMIT_EXCEEDED,
                              execution_time_ms=user_run_result.execution_time_ms,
                              memory_used_kb=user_run_result.memory_used_kb)

    if user_run_result.status == 'oom-kill':
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
                              execution_time_ms=user_run_result.execution_time_ms,
                              memory_used_kb=user_run_result.memory_used_kb)

    if user_run_result.exit_code != 0:
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.RUNTIME_ERROR,
                              stderr=user_run_result.stderr, execution_time_ms=user_run_result.execution_time_ms,
                              memory_used_kb=user_run_result.memory_used_kb)

    if user_run_result.status != 'success':
        return TestCaseResult(test_case_name=test_case.name, status=SubmissionStatus.INTERNAL_ERROR,
                              stderr=user_run_result.stderr or "Unknown internal error in sandbox engine.")

    td = None
    try:
        full_stdout = user_run_result.stdout or ""
        display_stdout = (full_stdout[:4096] + '...') if len(full_stdout) > 4096 else full_stdout

        if problem.validator_type == 'custom' and problem.validator_code:
            td = tempfile.mkdtemp(prefix=f"validator_{submission_id.hex[:8]}_")
            user_out_path = os.path.join(td, "user.out")
            test_in_path = os.path.join(td, "test.in")
            test_exp_path = os.path.join(td, "test.exp")

            with open(user_out_path, 'w') as f:
                f.write(full_stdout)
            with open(test_in_path, 'w') as f:
                f.write(test_case.input_content or "")
            with open(test_exp_path, 'w') as f:
                f.write(test_case.output_content or "")

            validator_result = await run_sandboxed(
                code=problem.validator_code,
                language=problem.validator_language,
                run_input=None,
                time_limit_sec=problem.validator_time_limit_sec,
                memory_limit_mb=problem.validator_memory_limit_mb,
                unit_name_prefix=f"val-{submission_id.hex[:8]}",
                extra_bind_files=[
                    (test_in_path, "/sandbox/input.txt"),
                    (user_out_path, "/sandbox/user.out"),
                    (test_exp_path, "/sandbox/expected.out")
                ],
                cmd_args=[
                    "/sandbox/input.txt",
                    "/sandbox/user.out",
                    "/sandbox/expected.out"
                ]
            )

            is_validator_failure = (
                    validator_result.status not in ('success', 'runtime_error')
                    or validator_result.exit_code is None
                    or validator_result.exit_code < 0
            )

            if is_validator_failure:
                return TestCaseResult(
                    test_case_name=test_case.name, status=SubmissionStatus.INTERNAL_ERROR,
                    stderr=f"Judge Validator Error: The validator failed to execute (Status: {validator_result.status}). Please contact an admin.",
                    execution_time_ms=user_run_result.execution_time_ms, memory_used_kb=user_run_result.memory_used_kb
                )

            status = SubmissionStatus.ACCEPTED if validator_result.exit_code == 0 else SubmissionStatus.WRONG_ANSWER

        else:
            td = tempfile.mkdtemp(prefix=f"diff_{submission_id.hex[:8]}_")
            user_out_path = os.path.join(td, "user.out")
            test_exp_path = os.path.join(td, "test.exp")
            with open(user_out_path, 'w') as f:
                f.write(full_stdout)
            with open(test_exp_path, 'w') as f:
                f.write(test_case.output_content or "")

            diff_code = await asyncio.get_running_loop().run_in_executor(blocking_executor, diff_files, user_out_path,
                                                                         test_exp_path)
            status = SubmissionStatus.ACCEPTED if diff_code == 0 else SubmissionStatus.WRONG_ANSWER

        return TestCaseResult(
            test_case_name=test_case.name, status=status,
            stdout=display_stdout if status == SubmissionStatus.WRONG_ANSWER else None,
            stderr=user_run_result.stderr,
            execution_time_ms=user_run_result.execution_time_ms, memory_used_kb=user_run_result.memory_used_kb
        )

    finally:
        if td: shutil.rmtree(td, ignore_errors=True)


from typing import Optional, List, Dict


async def run_generator_in_sandbox(problem: Problem) -> Dict[str, Any]:
    if not problem.generator_code:
        return {"input": None, "output": None, "error": "Generator code not found in problem object.",
                "status": "error"}
    result = await run_sandboxed(
        code=problem.generator_code,
        language=problem.generator_language,
        run_input=None,
        time_limit_sec=int(problem.generator_time_limit_sec or 5.0),
        memory_limit_mb=problem.generator_memory_limit_mb or 256,
        unit_name_prefix="gen"
    )
    error_content: Optional[str] = None
    if result.status == 'compilation_error':
        error_content = "Generator " + (result.compilation_stderr or "compilation failed.")
    elif result.exit_code != 0:
        error_content = f"Generator script exited with error code {result.exit_code}. Status: {result.status}. Detail: {result.stderr or 'No error output.'}"
    elif result.status != 'success':
        error_content = f"Generator sandbox failed to execute. Status: {result.status}."

    return {
        "input": result.stdout,
        "output": result.stderr,
        "error": error_content,
        "execution_time_ms": result.execution_time_ms,
        "memory_used_kb": result.memory_used_kb,
        "status": "success" if error_content is None else "error"
    }


class SubmissionProcessingQueue:
    def __init__(self, worker_count: int):
        self._queue = asyncio.Queue()
        self._worker_count = worker_count
        self._workers: List[asyncio.Task] = []

    async def start_workers(self):
        if self._workers: return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._workers = [loop.create_task(self._worker(worker_id=i)) for i in range(self._worker_count)]

    async def stop_workers(self):
        if not self._workers: return
        for _ in self._workers: await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def enqueue(self, submission_id: str):
        await self._queue.put(submission_id)

    async def _worker(self, worker_id: int):
        while True:
            submission_id = await self._queue.get()
            if submission_id is None:
                self._queue.task_done()
                break
            try:
                await self._process_submission(submission_id, worker_id)
            except Exception as e:
                traceback.print_exc()
                await self._handle_error(submission_id, f"Worker processing failed: {e}")
            self._queue.task_done()

    async def _process_submission(self, submission_id: str, worker_id: int):
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            sub = crud_submission.submission.get(db, id_=submission_id)
            if not sub: return

            terminal_statuses = {s.value for s in SubmissionStatus if
                                 s not in [SubmissionStatus.PENDING, SubmissionStatus.RUNNING]}
            if sub.status in terminal_statuses: return

            sub.status = SubmissionStatus.RUNNING.value
            db.add(sub)
            db.commit()
            db.refresh(sub)

            problem = get_problem_by_id(sub.contest_id, sub.problem_id)
            if not problem:
                err = TestCaseResult(test_case_name="Setup", status=SubmissionStatus.INTERNAL_ERROR,
                                     stderr="Problem definition not found")
                crud_submission.submission.update_submission_results(db, db_obj=sub,
                                                                     status=SubmissionStatus.INTERNAL_ERROR.value,
                                                                     results=[err])
                return

            final_results: List[TestCaseResult] = []
            overall_status = SubmissionStatus.ACCEPTED

            sorted_test_cases = sorted(problem.test_cases, key=lambda tc: tc.name)

            for tc in sorted_test_cases:
                try:
                    res = await _judge_test_case(submission_id=uuid.UUID(submission_id), code=sub.code,
                                                 language=sub.language, problem=problem, test_case=tc)
                except Exception as e:
                    traceback.print_exc()
                    res = TestCaseResult(test_case_name=tc.name, status=SubmissionStatus.INTERNAL_ERROR,
                                         stderr=f"Executor error: {type(e).__name__}: {e}")

                final_results.append(res)
                if res.status != SubmissionStatus.ACCEPTED:
                    overall_status = res.status
                    break

            crud_submission.submission.update_submission_results(db, db_obj=sub, status=overall_status.value,
                                                                 results=final_results)
        except Exception as e:
            if db: db.rollback()
            raise
        finally:
            if db: db.close()

    async def _handle_error(self, submission_id: str, error_message: str):
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            sub = crud_submission.submission.get(db, id_=submission_id)
            if sub and sub.status != SubmissionStatus.INTERNAL_ERROR.value:
                err = TestCaseResult(test_case_name="Processing Failure", status=SubmissionStatus.INTERNAL_ERROR,
                                     stderr=f"Queue worker error: {error_message[:500]}")
                crud_submission.submission.update_submission_results(db, db_obj=sub,
                                                                     status=SubmissionStatus.INTERNAL_ERROR.value,
                                                                     results=[err])
        except Exception as db_err:
            if db: db.rollback()
        finally:
            if db: db.close()


QUEUE_WORKER_COUNT = (os.cpu_count() or 1)
submission_processing_queue = SubmissionProcessingQueue(worker_count=QUEUE_WORKER_COUNT)

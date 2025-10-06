import pytest
from app.sandbox.engine import run_sandboxed

pytestmark = pytest.mark.asyncio


async def test_run_sandboxed_python_success():
    code = "name = input()\nprint(f'Hello, {name}!')"
    run_input = "World"

    result = await run_sandboxed(
        code=code,
        language="python",
        run_input=run_input,
        time_limit_sec=2,
        memory_limit_mb=64
    )

    assert result.status == "success"
    assert result.exit_code == 0
    assert result.stdout.strip() == "Hello, World!"
    assert result.stderr is None
    assert result.compilation_stderr is None


async def test_run_sandboxed_cpp_compile_error():
    code = """
    #include <iostream>
    int main() {
        std::cout << "Hello" << std::endl
        return 0;
    }
    """

    result = await run_sandboxed(
        code=code,
        language="c++",
        run_input="",
        time_limit_sec=2,
        memory_limit_mb=64
    )

    assert result.status == "compilation_error"
    assert result.stdout is None
    assert "error: expected" in result.compilation_stderr.lower()


async def test_run_sandboxed_timeout():
    code = "while True: pass"

    result = await run_sandboxed(
        code=code,
        language="python",
        run_input="",
        time_limit_sec=1,
        memory_limit_mb=64
    )

    assert result.status == "timeout"

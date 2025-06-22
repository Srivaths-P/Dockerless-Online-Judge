import shutil

import pytest

from app.sandbox.engine import run_sandboxed

BWRAP_EXISTS = shutil.which("bwrap") is not None
GCC_EXISTS = shutil.which("gcc") is not None
GPP_EXISTS = shutil.which("g++") is not None

pytestmark = pytest.mark.sandbox


@pytest.mark.skipif(not BWRAP_EXISTS, reason="bubblewrap (bwrap) is not installed")
class TestSandbox:
    @pytest.mark.asyncio
    async def test_python_hello_world(self):
        code = "print('Hello, World!')"
        result = await run_sandboxed(code=code, language="python")
        assert result.status == "success"
        assert result.stdout.strip() == "Hello, World!"
        assert result.exit_code == 0

    @pytest.mark.skipif(not GCC_EXISTS, reason="gcc is not installed")
    @pytest.mark.asyncio
    async def test_c_tle(self):
        code = '#include <stdio.h>\nint main() { while(1); return 0; }'
        result = await run_sandboxed(code=code, language="c", time_limit_sec=1)
        assert result.status == "timeout"

    @pytest.mark.skipif(not GPP_EXISTS, reason="g++ is not installed")
    @pytest.mark.asyncio
    async def test_cpp_compile_error(self):
        code = '#include <iostream>\nint main() { std::cout << "hello" return 0; }'
        result = await run_sandboxed(code=code, language="c++")
        assert result.status == "compilation_error"
        assert "compilation_stderr" in result.model_dump()
        assert "expected" in result.compilation_stderr.lower()

    @pytest.mark.asyncio
    async def test_python_runtime_error(self):
        code = "print(1/0)"
        result = await run_sandboxed(code=code, language="python")
        assert result.status == "success"
        assert result.exit_code != 0
        assert "ZeroDivisionError" in result.stderr

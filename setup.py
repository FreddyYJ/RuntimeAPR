import subprocess
import setuptools # type: ignore
import sys
import os
from pathlib import Path

def get_version():
    import re
    v = re.findall(r"\nVERSION *= *\"([^\"]+)\"", Path("src/runtimeapr/slipcover.py").read_text())[0]
    return v

VERSION = get_version()
REPO_URL = "https://github.com/FreddyYJ/RuntimeAPR" # "https://github.com/plasma-umass/slipcover"

def get_description():
#    from pathlib import Path
    import re
    readme_md = Path("README.md")
    text = readme_md.read_text(encoding="utf-8")

    # rewrite any relative paths to version-specific absolute paths
    sub = r'\1' + REPO_URL + "/blob/v" + VERSION + r'/\2'
    text = re.sub(r'(src=")((?!https?://))', sub, text)
    text = re.sub(r'(\[.*?\]\()((?!https?://))', sub, text)

    return text

# Installing the Duet framework if not present and update path variables eitherway
path_to_duet = '/'.join(__file__.split('/')[:-1]) + '/src/runtimeapr/concolic/restoreStr/duet/'
subprocess.run([path_to_duet + "build"], shell=True)
subprocess.check_output(["opam", "env"])
if not os.path.exists(path_to_duet + 'main.native'):
    if subprocess.run(["make", "--directory", path_to_duet]).returncode:
        print("[Error] Unable to install the Duet Framework. Try doing it manually before retrying.")
        exit(127)

# If we're testing packaging, build using a ".devN" suffix in the version number,
# so that we can upload new files (as testpypi/pypi don't allow re-uploading files with
# the same name as previously uploaded).
# Numbering scheme: https://www.python.org/dev/peps/pep-0440

dev_build = '.dev' + Path('dev-build.txt').read_text().strip() if Path('dev-build.txt').exists() else ''

def cxx_version(v):
    return [f"-std={v}" if sys.platform != "win32" else f"/std:{v}"]

def platform_compile_args():
    # If flags are specified as a global env var use them,
    # this happens during conda build,
    # and is needed to override build configurations on osx
    flags = os.environ.get("CXXFLAGS", "").split()
    if flags:
        return flags

    # Otherwise default to a multi-arch build
    if sys.platform == 'darwin':
        return "-arch x86_64 -arch arm64 -arch arm64e".split()
    if sys.platform == 'win32':
        return ['/MT']  # avoids creating Visual Studio dependencies
    return []

def platform_link_args():
    if sys.platform != 'win32':
        return platform_compile_args() # clang/gcc is used
    return []

def limited_api_args():
    # We would like to use METH_FASTCALL, but that's only available in the
    # Python 3.10+ stable ABI, and we'd like to support Python 3.8+
    #
    # To re-enable, we also need setup.cfg with
    #
    # [bdist_wheel]
    # py-limited-api=cp310
    #
    #    return ['-DPy_LIMITED_API=0x030a0000']
    return []

setuptools.setup(
    name="runtimeapr",
    version=VERSION + dev_build,
    description="Automated Program Repair at Runtime",
    keywords="repair runtime",
    long_description=get_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/FreddyYJ/RuntimeAPR", # "https://github.com/plasma-umass/slipcover",
    author="YougJae Kim",
    author_email="",
    license="Apache License 2.0",
    packages=['runtimeapr','runtimeapr.concolic','runtimeapr.loop', 'runtimeapr.concolic.restoreStr', 'runtimeapr.concolic.restoreStr.utilsAST', 'runtimeapr.concolic.restoreStr.duet'],
    package_dir={'': 'src'},
    python_requires=">=3.8,<3.12",
    package_data={'': ['main.native']},
    install_requires=[
        "tabulate",
        "bytecode",
        "z3-solver",
        "astor",
        "py2cfg",
        "graphviz",
        "typing-extensions",
        "beniget",
        "gast",
        "importlib-resources",
        "torch",
        "torchvision",
        "torchaudio",
        "openai"
    ],
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows :: Windows 10"
    ]
)

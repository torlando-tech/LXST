import ctypes
import ctypes.util
import os
import sys
import platform
from typing import (
    Optional,
    Dict,
    List
)

_here = os.path.dirname(__file__)

class ExternalLibraryError(Exception):
    pass

architecture = platform.architecture()[0]

_windows_styles = ["{}", "lib{}", "lib{}_dynamic", "{}_dynamic"]

_other_styles = ["{}", "lib{}"]

if architecture == "32bit":
    for arch_style in ["32bit", "32" "86", "win32", "x86", "_x86", "_32", "_win32", "_32bit"]:
        for style in ["{}", "lib{}"]:
            _windows_styles.append(style.format("{}"+arch_style))
            
elif architecture == "64bit":
    for arch_style in ["64bit", "64" "86_64", "amd64", "win_amd64", "x86_64", "_x86_64", "_64", "_amd64", "_64bit"]:
        for style in ["{}", "lib{}"]:
            _windows_styles.append(style.format("{}"+arch_style))


run_tests = lambda lib, tests: [f(lib) for f in tests]

# Get the appropriate directory for the shared libraries depending 
# on the current platform and architecture
platform_ = platform.system()
lib_dir = None
if platform_ == "Darwin":
    lib_dir = "libs/macos"
elif platform_ == "Windows":
    if architecture == "32bit":
        lib_dir = "libs/win32"
    elif architecture == "64bit":
        lib_dir = "libs/win_amd64"


class Library:
    @staticmethod
    def load(names: Dict[str, str], paths: Optional[List[str]] = None, tests = []) -> Optional[ctypes.CDLL]:
        lib = InternalLibrary.load(names, tests)
        if lib is None:
            lib = ExternalLibrary.load(names["external"], paths, tests)
        return lib
        

class InternalLibrary:
    @staticmethod
    def load(names: Dict[str, str], tests) -> Optional[ctypes.CDLL]:
        # If we do not have a library directory, give up immediately
        if lib_dir is None:
            return None
            
        # Get the appropriate library filename given the platform
        try:
            name = names[platform_]
        except KeyError:
            return None

        # Attempt to load the library from here
        path = _here + "/" + lib_dir + "/" + name 
        try:
            lib = ctypes.CDLL(path)
        except OSError as e:
            return None

        # Check that the library passes the tests
        if tests and all(run_tests(lib, tests)):
            return lib

        # Library failed tests
        return None
        
# Cache of libraries that have already been loaded
_loaded_libraries: Dict[str, ctypes.CDLL] = {}

class ExternalLibrary:
    @staticmethod
    def load(name, paths = None, tests = []):
        if name in _loaded_libraries:
            return _loaded_libraries[name]
        if sys.platform == "win32":
            lib = ExternalLibrary.load_windows(name, paths, tests)
            _loaded_libraries[name] = lib
            return lib
        else:
            lib = ExternalLibrary.load_other(name, paths, tests)
            _loaded_libraries[name] = lib
            return lib

    @staticmethod
    def _is_android():
        """Check if running on Android (Chaquopy)."""
        return hasattr(sys, 'getandroidapilevel') or 'ANDROID_ROOT' in os.environ

    @staticmethod
    def load_other(name, paths = None, tests = []):
        # On Android, try loading from the app's native library path directly
        if ExternalLibrary._is_android():
            lib = ExternalLibrary._load_android(name, tests)
            if lib is not None:
                return lib

        os.environ["PATH"] += ";" + ";".join((os.getcwd(), _here))
        if paths: os.environ["PATH"] += ";" + ";".join(paths)

        for style in _other_styles:
            candidate = style.format(name)
            library = ctypes.util.find_library(candidate)
            if library:
                try:
                    lib = ctypes.CDLL(library)
                    if tests and all(run_tests(lib, tests)):
                        return lib
                except:
                    pass

    @staticmethod
    def _load_android(name, tests = []):
        """Load library on Android from the app's native library directory.

        On Android with Chaquopy, native libraries in jniLibs are extracted to
        the app's native library directory and can be loaded by name.
        We use RTLD_GLOBAL to ensure symbols are available to other libraries.
        """
        import sys
        print(f"[pyogg] Android library loader: attempting to load '{name}'", file=sys.stderr, flush=True)

        # Android library names to try
        android_names = [
            f"lib{name}.so",  # Standard Android naming
            name,              # As-is
            f"{name}.so",      # With .so extension
        ]

        # Use RTLD_GLOBAL to make symbols available globally (needed for dependent libs)
        # RTLD_NOW ensures all symbols are resolved immediately
        load_flags = ctypes.RTLD_GLOBAL

        for lib_name in android_names:
            try:
                print(f"[pyogg] Trying to load: {lib_name}", file=sys.stderr, flush=True)
                # Try loading with RTLD_GLOBAL first
                lib = ctypes.CDLL(lib_name, mode=load_flags)
                print(f"[pyogg] Successfully loaded: {lib_name}", file=sys.stderr, flush=True)
                if tests:
                    print(f"[pyogg] Running tests on {lib_name}...", file=sys.stderr, flush=True)
                    if all(run_tests(lib, tests)):
                        print(f"[pyogg] Tests passed for {lib_name}", file=sys.stderr, flush=True)
                        return lib
                    else:
                        print(f"[pyogg] Tests failed for {lib_name}", file=sys.stderr, flush=True)
                else:
                    return lib
            except OSError as e:
                print(f"[pyogg] Failed to load {lib_name}: {e}", file=sys.stderr, flush=True)
                continue

        print(f"[pyogg] Could not load library '{name}' on Android", file=sys.stderr, flush=True)
        return None

    @staticmethod
    def load_windows(name, paths = None, tests = []):
        os.environ["PATH"] += ";" + ";".join((os.getcwd(), _here))
        if paths: os.environ["PATH"] += ";" + ";".join(paths)
        
        not_supported = [] # libraries that were found, but are not supported
        for style in _windows_styles:
            candidate = style.format(name)
            library = ctypes.util.find_library(candidate)
            if library:
                try:
                    lib = ctypes.CDLL(library)
                    if tests and all(run_tests(lib, tests)):
                        return lib
                    not_supported.append(library)
                except WindowsError:
                    pass
                except OSError:
                    not_supported.append(library)
            

        if not_supported:
            raise ExternalLibraryError("library '{}' couldn't be loaded, because the following candidates were not supported:".format(name)
                                 + ("\n{}" * len(not_supported)).format(*not_supported))

        raise ExternalLibraryError("library '{}' couldn't be loaded".format(name))

        

        

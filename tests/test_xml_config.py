"""
Tests for XML configuration file parsing
"""

import pytest
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

from cs_binding_generator.main import parse_config_file


class TestXMLConfigParsing:
    """Test XML configuration file parsing functionality"""
    
    def test_parse_valid_config_file(self, temp_dir):
        """Test parsing a valid XML configuration file"""
        config_content = """
        <bindings>
            <library name="testlib" namespace="TestNamespace">
                <include file="/path/to/test.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 1
        assert pairs[0] == ("/path/to/test.h", "testlib")
        assert namespace == "TestNamespace"
        assert include_dirs == []
    
    def test_parse_multiple_libraries(self, temp_dir):
        """Test parsing config with multiple libraries"""
        config_content = """
        <bindings>
            <library name="lib1" namespace="Lib1Namespace">
                <include file="/path/to/lib1.h"/>
            </library>
            <library name="lib2" namespace="Lib2Namespace">
                <include file="/path/to/lib2a.h"/>
                <include file="/path/to/lib2b.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 3
        assert pairs[0] == ("/path/to/lib1.h", "lib1")
        assert pairs[1] == ("/path/to/lib2a.h", "lib2")
        assert pairs[2] == ("/path/to/lib2b.h", "lib2")
        # Should use namespace from first library
        assert namespace == "Lib1Namespace"
        assert include_dirs == []
    
    def test_parse_config_without_namespace(self, temp_dir):
        """Test parsing config without namespace specification"""
        config_content = """
        <bindings>
            <library name="testlib">
                <include file="/path/to/test.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 1
        assert pairs[0] == ("/path/to/test.h", "testlib")
        assert namespace is None
        assert include_dirs == []
    
    def test_parse_config_with_class_attributes(self, temp_dir):
        """Test parsing config with custom class names"""
        config_content = """
        <bindings>
            <library name="lib1" class="CustomLib1" namespace="TestNamespace">
                <include file="/path/to/lib1.h"/>
            </library>
            <library name="lib2" class="CustomLib2">
                <include file="/path/to/lib2.h"/>
            </library>
            <library name="lib3">
                <include file="/path/to/lib3.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 3
        assert pairs[0] == ("/path/to/lib1.h", "lib1")
        assert pairs[1] == ("/path/to/lib2.h", "lib2")
        assert pairs[2] == ("/path/to/lib3.h", "lib3")
        assert namespace == "TestNamespace"
        assert include_dirs == []
        assert library_class_names == {"lib1": "CustomLib1", "lib2": "CustomLib2", "lib3": "NativeMethods"}
    
    def test_parse_config_missing_library_name(self, temp_dir):
        """Test parsing config with missing library name attribute"""
        config_content = """
        <bindings>
            <library>
                <include file="/path/to/test.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        with pytest.raises(ValueError, match="Library element missing 'name' attribute"):
            parse_config_file(str(config_file))
    
    def test_parse_config_missing_include_file(self, temp_dir):
        """Test parsing config with missing include file attribute"""
        config_content = """
        <bindings>
            <library name="testlib">
                <include/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        with pytest.raises(ValueError, match="Include element.*missing 'file' attribute"):
            parse_config_file(str(config_file))
    
    def test_parse_config_wrong_root_element(self, temp_dir):
        """Test parsing config with wrong root element"""
        config_content = """
        <wrongroot>
            <library name="testlib">
                <include file="/path/to/test.h"/>
            </library>
        </wrongroot>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        with pytest.raises(ValueError, match="Expected root element 'bindings'"):
            parse_config_file(str(config_file))
    
    def test_parse_config_invalid_xml(self, temp_dir):
        """Test parsing invalid XML"""
        config_content = """
        <bindings>
            <library name="testlib">
                <include file="/path/to/test.h"
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        with pytest.raises(ValueError, match="XML parsing error"):
            parse_config_file(str(config_file))
    
    def test_parse_config_file_not_found(self):
        """Test parsing non-existent config file"""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            parse_config_file("/nonexistent/config.xml")
    
    def test_parse_real_config_file(self, temp_dir):
        """Test parsing the actual LibTCOD config file format"""
        config_content = """
        <bindings>
            <library name="libtcod" namespace="Libtcod">
                <include file="/usr/include/libtcod/libtcod.h"/>
            </library>
            <library name="SDL3" namespace="SDL3">
                <include file="/usr/include/SDL3/SDL.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "cs-bindings.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 2
        assert pairs[0] == ("/usr/include/libtcod/libtcod.h", "libtcod")
        assert pairs[1] == ("/usr/include/SDL3/SDL.h", "SDL3")
        assert namespace == "Libtcod"
        assert include_dirs == []
    
    def test_config_with_whitespace_handling(self, temp_dir):
        """Test that whitespace in config values is properly handled"""
        config_content = """
        <bindings>
            <library name=" testlib " namespace=" TestNamespace ">
                <include file=" /path/to/test.h "/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 1
        assert pairs[0] == ("/path/to/test.h", "testlib")  # Should be stripped
        assert namespace == "TestNamespace"  # Namespace stripped in new impl
        assert include_dirs == []
    
    def test_config_with_global_include_directories(self, temp_dir):
        """Test parsing config with global include directories"""
        config_content = """
        <bindings>
            <include_directory path="/usr/include"/>
            <include_directory path="/usr/local/include"/>
            <library name="testlib" namespace="TestNamespace">
                <include file="/path/to/test.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 1
        assert pairs[0] == ("/path/to/test.h", "testlib")
        assert namespace == "TestNamespace"
        assert include_dirs == ["/usr/include", "/usr/local/include"]
    
    def test_config_with_library_specific_include_directories(self, temp_dir):
        """Test parsing config with library-specific include directories"""
        config_content = """
        <bindings>
            <include_directory path="/usr/include"/>
            <library name="lib1" namespace="Lib1Namespace">
                <include_directory path="/usr/include/lib1"/>
                <include file="/path/to/lib1.h"/>
            </library>
            <library name="lib2">
                <include_directory path="/usr/include/lib2"/>
                <include file="/path/to/lib2.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 2
        assert pairs[0] == ("/path/to/lib1.h", "lib1")
        assert pairs[1] == ("/path/to/lib2.h", "lib2")
        assert namespace == "Lib1Namespace"
        assert set(include_dirs) == {"/usr/include", "/usr/include/lib1", "/usr/include/lib2"}
    
    def test_config_missing_include_directory_path(self, temp_dir):
        """Test parsing config with missing include directory path attribute"""
        config_content = """
        <bindings>
            <include_directory/>
            <library name="testlib">
                <include file="/path/to/test.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        with pytest.raises(ValueError, match="Include directory element missing 'path' attribute"):
            parse_config_file(str(config_file))
    
    def test_fatal_parse_errors_cause_immediate_failure(self, temp_dir):
        """Test that fatal parsing errors cause immediate failure with clear error messages"""
        from cs_binding_generator.generator import CSharpBindingsGenerator
        
        # Create a header that includes a non-existent file
        header_file = temp_dir / "test.h"
        header_file.write_text('#include "nonexistent.h"\\nint test_func();')
        
        generator = CSharpBindingsGenerator()
        
        # Should fail immediately with RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate(
                [(str(header_file), "testlib")],
                output=str(temp_dir),
                include_dirs=[str(temp_dir)]  # Include dir provided but file still missing
            )
        
        error_msg = str(exc_info.value)
        assert "Fatal parsing errors" in error_msg
        assert "nonexistent.h" in error_msg
        assert "Check include directories" in error_msg
    
    def test_parse_config_with_using_statements(self, temp_dir):
        """Test parsing config with using statements in libraries"""
        config_content = """
        <bindings>
            <library name="lib1" namespace="Lib1">
                <using namespace="System"/>
                <using namespace="System.Collections"/>
                <include file="/path/to/lib1.h"/>
            </library>
            <library name="lib2" namespace="Lib2">
                <using namespace="System.IO"/>
                <include file="/path/to/lib2.h"/>
            </library>
        </bindings>
        """
        
        config_file = temp_dir / "config.xml"
        config_file.write_text(config_content)
        
        pairs, namespace, include_dirs, renames, removals, library_class_names, library_namespaces, library_using_statements = parse_config_file(str(config_file))
        
        assert len(pairs) == 2
        assert pairs[0] == ("/path/to/lib1.h", "lib1")
        assert pairs[1] == ("/path/to/lib2.h", "lib2")
        assert namespace == "Lib1"  # First namespace found
        assert include_dirs == []
        assert library_namespaces == {"lib1": "Lib1", "lib2": "Lib2"}
        assert library_using_statements == {
            "lib1": ["System", "System.Collections"],
            "lib2": ["System.IO"]
        }
    
    @pytest.fixture
    def temp_dir(self):
        """Fixture for temporary directory"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
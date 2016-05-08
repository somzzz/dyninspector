# dyninspector
Diploma Project

## Project Requirements

- 32bit Unix system
- pyhton pyside
- lldb-3.6

## Get the Project

```
git clone https://github.com/somzzz/dyninspector
```

## Install Dependencies

On a Debian distribution with `apt` you can run the `setup` script, found in the project root directory, to automatically install the dependencies:

```
./setup
```

For any other distribution, use the preferred tools and make sure the following are installed:
- python 2.7
- [pyside](http://pyside.readthedocs.io/en/latest/building/linux.html)
- [lldb-3.6](http://lldb.llvm.org/)

## Setup Issues

### no.1 LLDB Symlinks

After installing `lldb`, you might receive the following error:

```
Traceback (most recent call last):
  File "dyninspector.py", line 12, in <module>
    from dynlldb import DynLldb
  File "/home/illaoi/dyninspector/src/dynlldb.py", line 7, in <module>
    import lldb
  File "/usr/lib/python2.7/dist-packages/lldb/__init__.py", line 52, in <module>
    _lldb = swig_import_helper()
  File "/usr/lib/python2.7/dist-packages/lldb/__init__.py", line 44, in swig_import_helper
    import _lldb
ImportError: No module named _lldb
```

If this happens, then the symlinks to the `lldb` module might be broken. Follow [these instructions](http://stackoverflow.com/questions/30869945/how-to-import-lldb-in-a-python-script) to fix them.


## Run the Tool

```
cd src/
python dyninspector.py
```

## Tool Usage

The tool can inspect ELF 32-bit LSB executables, Intel 80386.
A sample C program can be found in the c_samples directory of the project. To build the program:

```
cd c_sample
make
```

You can then open it from the DynInspector gui menu (Open ELF executable button).

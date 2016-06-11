# dyninspector
Diploma Project

Please send any feedback via [this form](https://docs.google.com/forms/d/1X-_MuDogIjQN7RHOGBHhO0nEZIXxs44G3oKWxrThaSo/viewform).

## Project Requirements

- ***32 bit Unix system (works fine on Ubuntu 14.04)***
```
Note: lldb 3-6 does not function properly on Ubuntu 16.04 and for this reason this tool can't be used on that system.
If you encounter problems on any other 32bit Unix system, please let me know!
```
- pyhton pyside
- lldb-3.6
- Intel x86 ISA

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
A sample C program can be found in the c_samples directory of the project, but I enourage you to test your own executables.

The tool can only analyse serial code, parallel execution is not supported.

Also, be careful when testing blocking functions (eg sockets) as the tool will block as well and continue to the next
breakpoint set as soon as it leaves the blocking context.


To build the C program:

```
cd c_sample
make
```

You can then open it from the DynInspector gui menu (Open ELF executable button).

The tool has 2 distinct debug modes in order to make the processes clear:
- one for analysing the dynamic linking / lazy binding process
- one for analysing the dynamic loading process

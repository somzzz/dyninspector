all: lib main

lib:
	gcc -m32 -c -Wall -Werror -fpic foo.c
	gcc -m32 -shared -o libfoo.so foo.o
	sudo cp libfoo.so /usr/lib
	sudo chmod 0755 /usr/lib/libfoo.so
	sudo ldconfig

main:
	gcc -m32 sample.c -g -o sample -ldl -Wall

clean:
	rm *o sample

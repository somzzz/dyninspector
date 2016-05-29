#include <stdio.h>
#include <sys/stat.h>
#include <dlfcn.h>

int main(void) {
	int rc;
	void *handle;
	char *error;
	void  (*foo_function)(void);

	printf("Hello world!");
	rc = chmod("/etc/passwd", 0444);
	printf("%d", rc);

	handle = dlopen("/usr/lib/libfoo.so", RTLD_LAZY);
	if (!rc)
		return -1;
      
    foo_function = dlsym(handle, "foo");
    if ((error = dlerror()) != NULL)
    	return -1;

    (*foo_function)();

    dlclose(handle);
	
	return 0;
}

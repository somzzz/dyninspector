#include <stdio.h>
#include <sys/stat.h>

int main(void) {

	printf("Hello world!");
	int rc = chmod("/etc/passwd", 0444);
	printf("%d", rc);
	
	return 0;
}

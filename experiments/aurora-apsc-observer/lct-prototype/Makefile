obj-m += lct_probe.o

ifndef KBUILD_ROOT
$(error Set KBUILD_ROOT to the exact reviewed ABI 3 kernel build tree)
endif

.PHONY: all clean
all:
	$(MAKE) -C $(KBUILD_ROOT) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KBUILD_ROOT) M=$(CURDIR) clean

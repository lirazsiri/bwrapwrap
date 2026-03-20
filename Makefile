PREFIX   ?= $(HOME)/.local
MANDIR   ?= $(PREFIX)/share/man/man1

.PHONY: install uninstall test

install:
	pipx install .
	install -d $(MANDIR)
	install -m 644 bww.1 $(MANDIR)/bww.1

uninstall:
	pipx uninstall bwrapwrap
	rm -f $(MANDIR)/bww.1

test:
	pytest tests/ -v

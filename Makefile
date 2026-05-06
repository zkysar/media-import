SHELL := /bin/bash
PROJECT_DIR := $(shell pwd)
BIN_LINK := $(HOME)/.local/bin/media-import
COMP_LINK := $(HOME)/.zsh/completions/_media-import

.PHONY: install uninstall test help

help:
	@echo "Targets:"
	@echo "  install    symlink media-import + completion into PATH/fpath"
	@echo "  uninstall  remove those symlinks"
	@echo "  test       run unittest discover on tests/"
	@echo
	@echo "Note: canonical install on this machine is via dotfiles"
	@echo "(dots bootstrap && dots link). Makefile install is for"
	@echo "stand-alone use without the dotfiles repo."

install:
	@chmod +x media-import
	@mkdir -p $(HOME)/.local/bin $(HOME)/.zsh/completions
	@ln -sf $(PROJECT_DIR)/media-import $(BIN_LINK)
	@ln -sf $(PROJECT_DIR)/completions/_media-import $(COMP_LINK)
	@echo "linked: $(BIN_LINK) -> $(PROJECT_DIR)/media-import"
	@echo "linked: $(COMP_LINK) -> $(PROJECT_DIR)/completions/_media-import"
	@echo "run 'exec zsh' (or open a new shell) to load completion."

uninstall:
	@rm -f $(BIN_LINK)
	@rm -f $(COMP_LINK)
	@echo "removed symlinks (or they didn't exist)"

test:
	@cd $(PROJECT_DIR) && python3 -m unittest discover tests

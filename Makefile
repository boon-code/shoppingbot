WHEEL ?= 1
VENV ?= 1
VIRTUALENV ?= 0
TIDY ?= 0
PYTHON_VERSION ?= 3

-include buildconfig.mk

PYTHON := "python$(PYTHON_VERSION)"

ifeq ($(VIRTUALENV),1)
VENV_CREATE := virtualenv -p $(PYTHON) env
else
VENV_CREATE := $(PYTHON) -m venv env
endif

ifeq ($(VENV),1)
VENV_DEP := env/bin/activate
VENV_PREP := NOREG=1 . env/bin/activate;
endif

ifeq ($(PYTHON_VERSION),3)
PIP := pip3
else
PIP := pip
endif

PACKAGE := shopbot

.PHONY: all
all: info

.PHONY: info
info:
	@echo "Targets:"
	@echo " - install ......... Make and install $(PACKAGE) package"
	@echo " - uninstall ....... Remove $(PACKAGE) package"
	@echo " - clean ........... Clean up build environment"
	@echo "Variables:"
	@echo " - WHEEL      (1/0): Set to 1 to use python wheels [current: $(WHEEL)]"
	@echo " - VENV       (1/0): Use virtualenv for install/uninstall [current: $(VENV)]"
	@echo " - VIRTUALENV (1/0): Use virtualenv rather than venv [current: $(VIRTUALENV)]"
	@echo " - TIDY       (1/0): Clean up after 'install' [current: $(TIDY)]"
	@echo " - PYTHON_VERSION:   Python version to use [current: $(PYTHON_VERSION)]"

$(VENV_DEP): requirements.txt
	( \
                [ -d "env" ] || { $(VENV_CREATE) && CREATED=1; }; \
                $(VENV_PREP) $(PIP) install -r requirements.txt; \
                touch env/bin/activate; \
                [ "${CREATED:=0}" = "0" ] || echo '[ -n "$${NOREG}" ] || eval "$$(register-python-argcomplete shoppingbot)"' >> env/bin/activate; \
	)

.PHONY: prepare
prepare: $(VENV_DEP)


.PHONY: build
build: $(VENV_DEP)
ifeq ($(WHEEL),1)
	( $(VENV_PREP) $(PYTHON) setup.py bdist_wheel; )
else
	( $(VENV_PREP) $(PYTHON) setup.py build; )
endif

.PHONY: install
install: build $(VENV_DEP)
ifeq ($(WHEEL),1)
	( $(VENV_PREP) $(PIP) install --upgrade dist/*.whl; )
else
	( $(VENV_PREP) $(PYTHON) setup.py install; )
endif
ifeq ($(TIDY),1)
	rm -rf ./build ./dist *.egg-info
endif

.PHONY: uninstall
uninstall: $(VENV_DEP)
	( $(VENV_PREP) $(PIP) uninstall -y $(PACKAGE); )

.PHONY: clean
clean:
	( rm -rf ./build ./dist *.egg-info ./env && \
        find . -name "__pycache__" -type d -exec rm -r "{}" \; ; )

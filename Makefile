.DEFAULT_GOAL := test

test:
	pylint tap_ga360 --disable missing-function-docstring,missing-class-docstring,missing-module-docstring,too-many-locals,invalid-name,line-too-long

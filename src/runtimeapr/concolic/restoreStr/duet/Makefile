ifdef DEBUG
	DEBUG="debug"
endif
all: main
	
main:
	ocamlbuild -use-ocamlfind src/main.native -tag $(DEBUG)

clean:
	ocamlbuild -clean

.PHONY: main

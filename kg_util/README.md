# Libraries for working with Data Commons KG

## MCF Parser

`mcf_parser` includes helper functions to parse files in [MCF
format](https://github.com/datacommonsorg/data/blob/master/docs/mcf_format.md).

### `mcf_parser.mcf_to_triples(mcf_file)`

Parses file containing a Node MCF graph into triples.

Arguments:

-  `mcf_file (file object)` - An MCF File object opened for read.

Returns an Iterable of triples. Each triple has four string values:

  ```
  [ <subject-id>, <property>, <object-id or object-value>, <'ID' | 'VALUE'>]
  ```

Also refer to `mcf_parser_test.py` for usage.

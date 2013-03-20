#!/usr/bin/env python

# DONE Add argument processing and a main.
# DONE yylex takes a (void) parameter Tuple, so probably need a
#       wrapper to keep the compiler happy so can throw away
#       the incoming parameter list?
#       --> NO! METH_NOARGS
# DONE Change the import in module init.
# ____ Does the imported module need to be reference counted?
# DONE Handle EOF same way as ply lexer.
# ____ Implement yyin_init -- need fdopen()
# ____ Doc note: User-defined functions in section 3 should be
#        declared static so that they are not exposed to the linker
#        in order to conform to Python C extension conventions.
# ____ Consider re-writing buildToken to be a Py_Builder pass-through
#        to simplify user calls.  Or to make a builder-style call a
#        wrapper around the lower level function.
#        buildToken(lineno, lexpos, tokentype, format, ...)
#        TOK(N)  TOK_I(N,I) TOK_S(N,S) TOK_C(N,C)
#        format == "" is no value
#        format != "" is passed directly to Py_VaBuildValue

import argparse

def processArgs():
    global args
    ap = argparse.ArgumentParser()
    ap.add_argument('filename', 
        help='File name in the form name.l.in, name.l is produced.')
    ap.add_argument('--extension-name','-e', type=str, 
        action='store',required=True, dest='extensionname',
        help='Name of Python extension.')
    ap.add_argument('--token-mod','-m', type=str, default='ply.lex', 
        action='store', dest='tokenmod',
        help='Name of Python module defining LexToken.')
    args = ap.parse_args()
    l = args.filename.split('.')
    if l[-1] != 'in':
        raise ValueError
    args.filenameOut = '.'.join(l[:-1])

# Write the declarations section boiler plate. 
def put_decls(f, trigger):
    f.write('/* From phlex ' + trigger + ' */\n')
    f.write(
'''#define YY_DECL static PyObject* yylex (void)
static PyObject *mod; /* Points to the module providing Class LexToken(object). */
static PyObject *token_cls; /* Caches lookup of the Class LexToken(object). */
PyObject *buildToken(char *tokentype, int hasval, PyObject *value, int lineno, int lexpos);
static long glineno = 0;
static long glexpos = 0;
#define PHTOK(T) buildToken((T), 0, NULL, glineno, glexpos)
#define PHTOKV(T,V) buildToken((T), 1, (V), glineno, glexpos)
/* End phlex */

''')


# Do reference counts need to be incremented on the import??

# NULL is error return from Py_<builder> calls.  Need to tweak
# buildToken() function to handle that better.

def put_funcs(f, trigger, extName, tokenModule):
    f.write('/* From phlex ' + trigger + ' */\n');
    f.write('\n'.join([
'/* Declare the method table for the lexer class.*/',
'static PyMethodDef {0:s}Methods[] = '.format(extName) + '{',
'    {"lex", yylex_wrapped, METH_NOARGS, "Return one LexToken per call."}',
'    {"yyin_init", yyin_init, METH_VARARGS,',
'        "Initialize yyin from open Python file."}',
'    { NULL, NULL, 0, NULL}\n}\n',
'',
'/* Extension module initialization. */',
'PyMODINIT_FUNC\ninit{0:s}(void)\n'.format(extName),
'{',
'    (void) Py_InitModule("{0:s}", {0:s}Methods);'.format(extName),
'    /* Capture a pointer to the LexToken class. */',
'    PyObject *fromlist;',
'    PyObject *mod; /* Module that provides Class LexToken(object) */',
'    fromlist = PyBuildValue("[s]","LexToken");',
'    mod = PyImport_ImportModuleEx("{0:s}", NULL, NULL, fromlist);\n'.
        format(tokenModule),
'    token_cls = PyObject_GetAttrStr(mod, "LexToken")',
'    Py_DECREF(fromlist);',
'}',
    ]))
    
    f.write(
'''/* Python calls with parameters, yylex is parameterless, so
   yylex_wrapped() simply ignores the parameters. */
static PyObject *yylex_wrapped(PyObject *self, PyObject *args)
{
    return yylex();
}
'''
)

    f.write(
'''static PyObject *buildToken(char *tokentype, int hasval, PyObject *value,
    long lineno, long lexpos)
{
    /* Build an instance of LexToken and return a pointer to it, or NULL.
       If hasval is non-zero, value must be non-NULL and point to a PyObject.
       if hasval is zero, the value attr of the LexToken instance is set to
       be the same as tokentype.  If hasval is false, value MUST be NULL.
       If tokentype is NULL, then buildToken returns a Py_None instance to
       indicate end-of-file to the calling parser. 
       Note that the object reference owned by the *value parameter
       is "stolen" by this function! */

    /* Maintainer note: Be sure to init all temporary PyObject pointers to NULL
       because the error exit code simply calls PyXDECREF() on world+dog. */
       
    PyObject *tok = NULL; /* The LexToken to be returned. */
    
    /* Temps for building Python instances of the token attributes. */
    PyObject *po_tokentype = NULL;
    PyObject *po_lineno = NULL;
    PyObject *po_lexpos = NULL;
    
    /* Handle the end-of-file case. Note early-out return. */
    if (tokentype == NULL)
    {
        tok = Py_None;
        Py_INCREF(tok);
        return tok;
    }
    
    /* Create an instance of LexToken. */
    if ((tok = PyObject_CallFunctionObjArgs(token_cls,NULL)) == NULL) goto error;
    
    /* Create Python object instances for token values. */
    if ((po_tokentype = PyString_FromString(tokentype)) == NULL) goto error;
    if ((po_lineno = PyInt_FromLong(lineno)) == NULL) goto error;
    if ((po_lexpos = PyInt_FromLong(lexpos)) == NULL) goto error;

    /* If !hasval, then set value to be the same as tokentype. */
    if (hasval == 0)
    {
        value = po_tokentype;
        Py_INCREF(value);
    }
    else
    {
        /* When value == NULL, we assume that the user's Py<builder> call
           failed and returned NULL, so we handle that error here. */
        if (value == NULL) goto error;
    }
    
    /* Set the token attributes in the instance of tok. */
    if (PyObject_SetAttrString (tok, "type", po_tokentype) < 0) goto error;
    if (PyObject_SetAttrString (tok, "value", value) < 0) goto error;
    if (PyObject_SetAttrString (tok, "lineno", po_lineno) < 0) goto error;
    if (PyObject_SetAttrString (tok, "lexpos", po_lexpos) < 0) goto error;

    /* Phew! Done.
       Note that ownership of the reference we are holding to tok gets
       passed to the caller.  Ownership of the references po_tokentype,
       po_lineno, and po_lexpos were given to tok.  The reference owned
       by the incoming parameter "value" is was given to tok. */
    return tok;
    
error:
    /* clean up ref counts */
    Py_XDECREF(po_lexpos);
    Py_XDECREF(po_lineno);
    Py_XDECREF(po_tokentype);
    Py_XDECREF(value); /* We promise to steal it, so on failure we eat it. */
    Py_XDECREF(tok);
    
    return NULL;
}
''')

    f.write('\n'.join([
'static PyObject *yyin_init(PyObject *self, PyObject *args)',
'{',
'}',
'\n\n',
    ]))
    f.write('/* End phlex */\n')

def put_yywrap(f, trigger):
    f.write('/* From phlex ' + trigger + ' */\n');
    f.write('int yywrap() {return 1}\n/* End phlex */\n')
    

processArgs()

with open(args.filename) as fin:
    with open(args.filenameOut,'w') as fout:
        for ln in fin:
            lns = ln.rstrip()
            if lns == '@PLY_HOOKS_DECL@':
                put_decls(fout, '@PLY_HOOKS_DECL@')
            elif lns == '@PLY_HOOKS_PROC@':
                put_funcs(fout, '@PLY_HOOKS_PROC@', args.extensionname,
                     args.tokenmod)
            elif lns == '@YYWRAP@':
                put_yywrap(fout, '@YYWRAP@')
            else:
                fout.write(ln)
            
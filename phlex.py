#!/usr/bin/env python
# A pre-processor for flex .l files that wraps the resulting lexer
# as a Python C Extension.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# To do list:
# ____ Does the imported module need to be reference counted?
# ____ Doc note: User-defined functions in section 3 should be
#        declared static so that they are not exposed to the linker
#        in order to conform to Python C extension conventions.

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
    ap.add_argument('--setup', '-S', action='store_true', 
        help='Generate setup.py file.')
    args = ap.parse_args()
    l = args.filename.split('.')
    if l[-1] != 'in':
        raise ValueError
    args.filenameOut = '.'.join(l[:-1])

# Write the declarations section boiler plate. 
def put_decls(f, trigger):
    "Write the phlex declarations that live between %{ and %} in the .l file."
    f.write('/* From phlex ' + trigger + ' */\n')
    f.write(
'''#define YY_DECL static PyObject* yylex (void)
static PyObject *token_cls; /* Caches lookup of the Class LexToken(object). */
static PyObject *buildToken(long lineno, long lexpos, char *tokentype,
    char *format, ...);
static long glineno = 1;
static long glexpos = 0;
#define TOK(N) buildToken(glineno, glexpos, N, NULL)
#define TOK_L(N,L) buildToken(glineno, glexpos, N, "l", L)
#define TOK_S(N,S) buildToken(glineno, glexpos, N, "s", S)
#define TOK_C(N,C) buildToken(glineno, glexpos, N, "c", C)
#define TOK_D(N,D) buildToken(glineno, glexpos, N, "d", D)
#define TOK_EOF buildToken(glineno, glexpos, NULL, NULL)
#define RTN(N) {PyObject *t=TOK(N); glexpos+=strlen(yytext); return t;}
#define RTN_L(N,L) {PyObject *t=TOK_L(N,L); glexpos+=strlen(yytext); return t;}
#define RTN_S(N,S) {PyObject *t=TOK_S(N,S); glexpos+=strlen(yytext); return t;}
#define RTN_C(N,C) {PyObject *t=TOK_C(N,C); glexpos+=strlen(yytext); return t;}
#define RTN_D(N,D) {PyObject *t=TOK_D(N,D); glexpos+=strlen(yytext); return t;}
/* End phlex */

''')

def put_funcs(f, trigger, extName, tokenModule):
    "Write the C functions that live in section 3 of the .l file."
    f.write('/* From phlex ' + trigger + ' */\n');
    
    f.write(
'''/* Python always passes parameters to extensions, but yylex is 
   parameterless, so yylex_wrapped() simply ignores the parameters. */
static PyObject *yylex_wrapped(PyObject *self, PyObject *args)
{
    return yylex();
}

'''
    )

    f.write(
'''static PyObject *yyin_init(PyObject *self, PyObject *args)
{
    /* yyin_init takes a single integer argument that is a 
       file descriptor to a file that has already been opened
       by the calling Python code. */
    int fd;
    FILE *infile;
    if (!PyArg_ParseTuple(args, "i", &fd))
        return NULL;
    infile = fdopen(fd, "r");
    if (!infile)
        return NULL;
    yyin = infile;
    Py_RETURN_NONE;
}

''')

    f.write('\n'.join([
'/* Declare the method table for the lexer class.*/',
'static PyMethodDef {0:s}Methods[] = '.format(extName) + '{',
'    {"lex", yylex_wrapped, METH_NOARGS, "Return one LexToken per call."},',
'    {"yyin_init", yyin_init, METH_VARARGS,',
'        "Initialize yyin from the file descriptor of an open file."},',
'    { NULL, NULL, 0, NULL},\n};\n',
'',
'/* Extension module initialization. */',
'PyMODINIT_FUNC\ninit{0:s}(void)'.format(extName),
'{',
'    (void) Py_InitModule("{0:s}", {0:s}Methods);'.format(extName),
'    /* Capture a pointer to the LexToken class. */',
'    PyObject *fromlist;',
'    PyObject *mod; /* Module that provides Class LexToken(object) */',
'    fromlist = Py_BuildValue("[s]","LexToken");',
'    mod = PyImport_ImportModuleLevel("{0:s}", NULL, NULL, fromlist,-1);'.
        format(tokenModule),
'    token_cls = PyObject_GetAttrString(mod, "LexToken");',
'    Py_DECREF(fromlist);',
'}',
'\n\n',
    ]))
    

    f.write(
'''static PyObject *buildToken(long lineno, long lexpos, char *tokentype,
    char *format, ...)
{
    /* Build an instance of LexToken and return a PyObject pointer to it, 
       or return NULL on error.  If tokentype is NULL, then buildToken 
       returns a Py_None instance as the end-of-file indicator.
       If format is NULL, then the token value is set to be the same as
       tokentype.  If format is non-NULL, it is passed directly to 
       Py_VaBuildValue() along with any subsequent varargs, and the 
       result becomes the token value. */

    /* Maintainer note: Be sure to init all temporary PyObject pointers to NULL
       because the error exit code simply calls PyXDECREF() on world+dog. */
       
    PyObject *tok = NULL; /* The LexToken to be returned. */
    
    /* Temps for building Python instances of the token attributes. */
    PyObject *po_tokentype = NULL;
    PyObject *po_lineno = NULL;
    PyObject *po_lexpos = NULL;
    PyObject *po_value = NULL;
    va_list argp;
    
    /* Handle the end-of-file case as an early-out, returning None. */
    if (tokentype == NULL)
    {
        Py_RETURN_NONE;
    }
    
    /* Create an instance of LexToken. */
    if ((tok = PyObject_CallFunctionObjArgs(token_cls,NULL)) == NULL) goto error;
    
    /* Create Python object instances for token attributes. */
    if ((po_tokentype = PyString_FromString(tokentype)) == NULL) goto error;
    if ((po_lineno = PyInt_FromLong(lineno)) == NULL) goto error;
    if ((po_lexpos = PyInt_FromLong(lexpos)) == NULL) goto error;

    /* If format is NULL, then set value to be the same as tokentype. */
    if (format == NULL)
    {
        po_value = po_tokentype;
        Py_INCREF(po_value);
    }
    else
    {
        va_start(argp, format);
        po_value = Py_VaBuildValue(format, argp);
        if (po_value == NULL) goto error;
        va_end(argp);
    }
    
    /* Set the token attributes in the instance of tok. */
    if (PyObject_SetAttrString (tok, "type", po_tokentype) < 0) goto error;
    if (PyObject_SetAttrString (tok, "value", po_value) < 0) goto error;
    if (PyObject_SetAttrString (tok, "lineno", po_lineno) < 0) goto error;
    if (PyObject_SetAttrString (tok, "lexpos", po_lexpos) < 0) goto error;

    /* Phew! Done.
       Note that ownership of the reference we are holding to tok gets
       passed to the caller.  Ownership of the references po_tokentype,
       po_value, po_lineno, and po_lexpos were given to tok. */
    return tok;
    
error:
    /* clean up ref counts */
    Py_XDECREF(po_lexpos);
    Py_XDECREF(po_lineno);
    Py_XDECREF(po_tokentype);
    Py_XDECREF(po_value);
    Py_XDECREF(tok);
    
    return NULL;
}

''')

    f.write('/* End phlex */\n')

def put_yywrap(f, trigger):
    "Write a simple yywrap() function."
    f.write('/* From phlex ' + trigger + ' */\n');
    f.write('int yywrap() {return 1;}\n/* End phlex */\n')
    
def put_setup(f, extname):
    "Write a setup.py file specific for building this lexer."
    f.write('\n'.join([
'from distutils.core import setup, Extension',
'',
"module1 = Extension('{0:s}',".format(extname),
"    sources = ['lex.yy.c'],",
"    extra_compile_args = ['-DPYTHON_EXTENSION'])",
'',
"setup (name = '{0:s}',".format(extname),
"       version = '1.0',",
"       description = 'A flex lexer as a Python extension.',",
"       ext_modules = [module1])",
'',
    ]))

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
            
if args.setup:
    with open('setup.py', 'w') as fout:
        put_setup(fout, args.extensionname)
    

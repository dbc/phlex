from distutils.core import setup, Extension

module1 = Extension('calclex',
                    sources = ['lex.yy.c'])

setup (name = 'calclex',
       version = '1.0',
       description = 'A flex lexer for calculator demo.',
       ext_modules = [module1])

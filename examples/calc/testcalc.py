"Simple test driver for calclex extension."
import calclex

with open('testdata01.txt','r') as f:
    calclex.yyin_init(f.fileno())
    t = calclex.lex()
    while (t != None):
        print t
        t = calclex.lex()
    print t
    

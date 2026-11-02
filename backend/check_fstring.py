import ast

line = '                description=f"Prediction calibration {cal.id} for {cal.prediction_type} is in status \'{cal.status}\',"'

print(repr(line))

try:
    ast.parse(line)
    print('Valid')
except SyntaxError as e:
    print(f'Invalid: {e}')
import inspect
from typing import Callable, Any, Union, Dict
from functools import wraps
from langgraph.types import Command
from io import StringIO
from pydantic import BaseModel


def trace_node_info(_func=None, *, verbose=False):
    """Отслеживает изменения в нодах с гарантированно корректным выводом"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state: Union[Dict[str, Any], BaseModel], *args, **kwargs):
            if verbose:
                description = func.__doc__.strip() if func.__doc__ else "Нода без описания"
                executed_conditions = []
                if inspect.isfunction(func):
                    source_lines = inspect.getsource(func).split('\n')
                    source_code = '\n'.join(source_lines[1:])

                    def evaluate_conditions(code):
                        lines = code.split('\n')
                        conditions_stack = []
                        executed_in_block = False

                        for line in lines:
                            line = line.strip()
                            indent = len(line) - len(line.lstrip())

                            if line.startswith('if '):
                                condition = line[3:].split(':')[0].strip()
                                try:
                                    res = eval(condition, {"state": state}, {})
                                    if res:
                                        executed_conditions.append(condition)
                                        executed_in_block = True
                                    conditions_stack.append((indent, res))
                                except Exception:
                                    pass

                            elif line.startswith('elif '):
                                condition = line[5:].split(':')[0].strip()
                                if conditions_stack and conditions_stack[-1][0] == indent:
                                    if not executed_in_block:
                                        try:
                                            res = eval(condition, {"state": state}, {})
                                            if res:
                                                executed_conditions.append(condition)
                                                executed_in_block = True
                                            conditions_stack[-1] = (indent, res)
                                        except Exception:
                                            pass

                            elif line.startswith('else:'):
                                if conditions_stack and conditions_stack[-1][0] == indent:
                                    if not executed_in_block:
                                        executed_conditions.append("else")
                                        executed_in_block = True
                                    conditions_stack.pop()

                            if conditions_stack and indent < conditions_stack[-1][0]:
                                executed_in_block = False

                    evaluate_conditions(source_code)

            result = func(state, *args, **kwargs)
            if verbose:
                with StringIO() as output:
                    is_routing = isinstance(result, (str, Command))
                    node_symbol = "🔄" if is_routing else "⚙ ==>"
                    output.write(f"{node_symbol} Нода: {func.__name__} | {description}\n")

                    for el in executed_conditions:
                        output.write(f"  🎯 Срабатывание условия: {el} -> True\n")

                    if isinstance(result, Command):
                        output.write("   🚦 Управление графом через Command:\n")

                        if hasattr(result, 'update') and result.update:
                            changes = {}
                            for key, value in result.update["state"].items():
                                if isinstance(state, BaseModel):
                                    old_val = getattr(state.state.model_dump(), key, None)
                                    if old_val != value:
                                        changes[key] = (old_val, value)
                                else:
                                    old_val = state.get(key)
                                    if old_val != value:
                                        changes[key] = (old_val, value)

                            if changes:
                                output.write("   📊 Изменение state:\n")
                                for key, (old_val, new_val) in changes.items():
                                    output.write(f"      {key}: {old_val} → {new_val}\n")

                        output.write(f"   ➡️ Перенаправление к: {result.goto}\n")

                    elif isinstance(result, str):
                        output.write(f"   ➡️ Перенаправление к: {result}\n")

                    else:
                        if isinstance(result, dict):
                            changes = {
                                key: (
                                getattr(state, key, None) if isinstance(state, BaseModel) else state.get(key), value)
                                for key, value in result.items()
                                if (isinstance(state, BaseModel) and getattr(state, key, None) != value) or
                                   (not isinstance(state, BaseModel) and (key not in state or state[key] != value))
                            }
                        else:
                            changes = {
                                field: (getattr(state, field, None), getattr(result, field, None))
                                for field in result.__fields__
                                if getattr(state, field, None) != getattr(result, field, None)
                            } if isinstance(result, BaseModel) else {}

                        if changes:
                            output.write("   📊 Изменение state:\n")
                            for key, (old_val, new_val) in changes.items():
                                output.write(f"      {key}: {old_val} → {new_val}\n")

                    output.write("_" * 100)
                    output.write("\n")

                    print(output.getvalue(), end='', flush=True)

            return result

        return wrapper

    if _func is not None:
        return decorator(_func)

    return decorator

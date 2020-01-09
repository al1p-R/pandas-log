# -*- coding: utf-8 -*-

"""Main module."""

import warnings
from contextlib import contextmanager
from functools import wraps

import pandas as pd
import pandas_flavor as pf

from pandas_log import settings
from pandas_log.aop_utils import (keep_pandas_func_copy,
                                  restore_pandas_func_copy,)
from pandas_log.pandas_execution_stats import StepStats, get_execution_stats

__all__ = ["auto_enable", "auto_disable", "enable"]


ALREADY_ENABLED = False


def auto_disable():
    """ Restore original pandas method without the additional log functionality (statistics)
        Note: we keep the original methods using original_ prefix.
        :return: None
    """
    global ALREADY_ENABLED
    if not ALREADY_ENABLED:
        return

    for func in dir(pd.DataFrame):
        if func.startswith(settings.ORIGINAL_METHOD_PREFIX):
            restore_pandas_func_copy(func)
    ALREADY_ENABLED = False


@contextmanager
def enable(verbose=False, silent=False, full_signature=True, copy_ok=True):
    """ Adds the additional logging functionality (statistics) to pandas methods only for the scope of this
        context manager.

        :param verbose: Whether some inner functions should be recorded as well.
                        For example: when a dataframe being copied
        :param silent: Whether additional the statistics get printed
        :param full_signature: adding additional information to function signature
        :param copy_ok: whether the dataframe is allowed to be copied to calculate more informative metadata logs
        :return: None
    """

    auto_enable(verbose, silent, full_signature, copy_ok)
    yield
    auto_disable()


def auto_enable(verbose=False, silent=False, full_signature=True, copy_ok=True):
    """ Adds the additional logging functionality (statistics) to pandas methods.

        :param verbose: Whether some inner functions should be recorded as well.
                        For example: when a dataframe being copied
        :param silent: Whether additional the statistics get printed
        :param full_signature: adding additional information to function signature
        :param copy_ok: whether the dataframe is allowed to be copied to calculate more informative metadata logs
        :return: None
    """
    global ALREADY_ENABLED
    if ALREADY_ENABLED:
        return

    settings.DATAFRAME_METHODS_TO_OVERIDE.extend(
        settings.DATAFRAME_ADDITIONAL_METHODS_TO_OVERIDE
    )

    # Suppressing warning of the fact we override pandas functions.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for func in dir(pd.DataFrame):
            if func in settings.DATAFRAME_METHODS_TO_OVERIDE:
                keep_pandas_func_copy(pd.DataFrame, func)
                create_overide_pandas_func(
                    pd.DataFrame, func, verbose, silent, full_signature, copy_ok
                )
        for func in dir(pd.Series):
            if func in settings.SERIES_METHODS_TO_OVERIDE:
                keep_pandas_func_copy(pd.Series, func)
                create_overide_pandas_func(
                    pd.Series, func, verbose, silent, full_signature, copy_ok
                )
    ALREADY_ENABLED = True


def create_overide_pandas_func(cls, func, verbose, silent, full_signature, copy_ok):
    """ Create overridden pandas method dynamically with
        additional logging using DataFrameLogger

        Note: if we extracting _overide_pandas_method outside we need to implement decorator like here
              https://stackoverflow.com/questions/10176226/how-do-i-pass-extra-arguments-to-a-python-decorator

        :param cls: pandas class for which the method should be overriden
        :param func: pandas method name to be overridden
        :param silent: Whether additional the statistics get printed
        :param full_signature: adding additional information to function signature
        :param copy_ok: whether the dataframe is allowed to be copied to calculate more informative metadata logs
        :return: the same function with additional logging capabilities
    """

    def _run_method_and_calc_stats(
        fn, fn_args, fn_kwargs, input_df, full_signature, silent, verbose
    ):

        if copy_ok:
            # If we're ok to make copies, copy the input_df so that we can compare against the output of inplace methods
            try:
                # Will hit infinite recursion if we use the patched copy method so use the original
                original_input_df = getattr(input_df, settings.ORIGINAL_METHOD_PREFIX+'copy')(deep=True)
            except AttributeError:
                original_input_df = input_df.copy(deep=True)
        output_df, execution_stats = get_execution_stats(
            cls, fn, input_df, fn_args, fn_kwargs
        )
        if output_df is None:
            # The operation was strictly in place so we just call the dataframe the output_df as well
            output_df = input_df
        if copy_ok:
            # If this isn't true and the method was strictly inplace, input_df and output_df will just
            # point to the same object
            input_df = original_input_df

        step_stats = StepStats(
            execution_stats,
            cls,
            fn,
            fn_args,
            fn_kwargs,
            full_signature,
            input_df,
            output_df,
        )
        step_stats.log_stats_if_needed(silent, verbose, copy_ok)
        if isinstance(output_df, pd.DataFrame) or isinstance(
            output_df, pd.Series
        ):
            step_stats.persist_execution_stats()
        # Don't think there's any garbage collection we should do manually?
        return output_df

    def _overide_pandas_method(fn):
        if cls == pd.DataFrame:
            register_method_wrapper = pf.register_dataframe_method
        elif cls == pd.Series:
            register_method_wrapper = pf.register_series_method
        @register_method_wrapper
        @wraps(fn)
        def wrapped(*args, **fn_kwargs):

            input_df, fn_args = args[0], args[1:]
            output_df = _run_method_and_calc_stats(
                fn,
                fn_args,
                fn_kwargs,
                input_df,
                full_signature,
                silent,
                verbose,
            )
            return output_df

        return wrapped

    return exec(
        f"@_overide_pandas_method\ndef {func}(df, *args, **kwargs): pass"
    )


if __name__ == "__main__":
    pass

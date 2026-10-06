# Import xgboost before numpy/scipy/scikit-learn/pydantic are loaded anywhere in
# the app. On macOS arm64 its libomp can clash with an OpenMP runtime that was
# loaded earlier, which segfaults while the statistical model is unpickled.
# xgboost is optional (only the XGBoost-based statistical model needs it).
try:
    import xgboost  # noqa: F401
except ImportError:
    pass

"""Model runtimes, the adapters that drive them, and the pure helpers they share.

`ClassifierService` owns selection, recovery and admission; nothing here decides
which runtime runs, only how a chosen one loads, preprocesses and reports."""

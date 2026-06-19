from django.apps import AppConfig

class ErpConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'erp'

    def ready(self):
        import erp.signals

        # Monkeypatch Django context copy for Python 3.14.5 compatibility
        import copy
        from django.template import context

        def safe_base_context_copy(self):
            cls = self.__class__
            duplicate = cls.__new__(cls)
            duplicate.__dict__.update(self.__dict__)
            duplicate.dicts = self.dicts[:]
            return duplicate

        def safe_context_copy(self):
            duplicate = safe_base_context_copy(self)
            duplicate.render_context = copy.copy(self.render_context)
            return duplicate

        context.BaseContext.__copy__ = safe_base_context_copy
        context.Context.__copy__ = safe_context_copy



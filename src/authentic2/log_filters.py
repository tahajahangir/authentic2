import logging

class RequestContextFilter(logging.Filter):
    DEFAULT_USERNAME = '-'
    DEFAULT_IP = '-'
    DEFAULT_REQUEST_ID = '-'

    def filter(self, record):
        '''Add username, ip and request ID to the log record.

           Inspired by django-log-request-id
        '''
        from . import middleware
        request = middleware.StoreRequestMiddleware.get_request()
        user = self.DEFAULT_USERNAME
        ip = self.DEFAULT_IP
        request_id = self.DEFAULT_REQUEST_ID
        if not request is None:
            if hasattr(request, 'user') and request.user.is_authenticated():
                user = unicode(request.user).encode('utf-8')
            ip = request.META['REMOTE_ADDR']
            request_id = request.request_id
        record.user = user
        record.ip = ip
        record.request_id = request_id
        return True

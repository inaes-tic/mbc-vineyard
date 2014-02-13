#!/usr/bin/python
# -*- coding: utf-8 -*-
import logging
import threading
from gi.repository import GLib, Gio, GObject

import avahi
import dbus
from dbus.mainloop.glib import DBusGMainLoop


def parse_txt(txt):
    res = {}
    for rawrow in txt:
        # XXX: here we can get something other than 7bit ascii.
        # how are we supposed to interpret it?
        row = k = u''.join( unicode(x) for x in rawrow)
        if '=' in row:
            k,v = row.split('=')
            res[k] = v
        else:
            res[k] = None
    return res


# XXX: need to make this work with Gio.DBus.
class MBCZeroconfBrowser(GObject.GObject):
    """
    Very basic GObject wrapper around DBus and Avahi.
    It only fetches services announced for the '_MBC._tcp' protocol.

    Signals emmited:
        service-up (service_name, info):
            "service_name" is a unicode string.
            "info" is a dict with keys for host, port, domain, address, protocol and the
            txtRecord converted to a dict, parsing it as key=value. When no '=' is found,
            it defaults to None.

        service-down (service_name, info)
    """
    __gsignals__ = {
        'service-up': (GObject.SIGNAL_RUN_FIRST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_PYOBJECT)),
        'service-down': (GObject.SIGNAL_RUN_FIRST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_PYOBJECT)),
    }
    def __init__(self, domain='local'):
        GObject.GObject.__init__(self)
        self.domain = domain
        self.service_browsers = set()
        self.services = {}
        self.lock = threading.Lock()

        loop = DBusGMainLoop(set_as_default=False)
        self._bus = dbus.SystemBus(mainloop=loop)
        self.server = dbus.Interface(
                self._bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER), 
                avahi.DBUS_INTERFACE_SERVER)

        self.browse("_MBC._tcp")

    def browse(self, service):
        if service in self.service_browsers:
            return
        self.service_browsers.add(service)

        with self.lock:
            browser = dbus.Interface(self._bus.get_object(avahi.DBUS_NAME, 
                    self.server.ServiceBrowserNew(avahi.IF_UNSPEC, 
                            avahi.PROTO_INET, service, self.domain, dbus.UInt32(0))),
                    avahi.DBUS_INTERFACE_SERVICE_BROWSER)

            browser.connect_to_signal("ItemNew", self.item_new)
            browser.connect_to_signal("ItemRemove", self.item_remove)
            browser.connect_to_signal("AllForNow", self.all_for_now)
            browser.connect_to_signal("Failure", self.failure)

    def resolved(self, interface, protocol, name, service, domain, host, 
            aprotocol, address, port, txt, flags):

        name = unicode(name)
        info = {}
        for k,v in {
            'port':     port,
            'host':     host,
            'domain':   domain,
            'address':  address,
            'protocol': protocol,
        }.iteritems():
            info[k] = unicode(v)

        info['txtRecord'] = parse_txt(txt)

        self.services[name] = info
        self.emit('service-up', name, info)

    def failure(self, exception):
        logging.error("Browse error: %s", exception)

    def item_new(self, interface, protocol, name, stype, domain, flags):
        with self.lock:
            self.server.ResolveService(interface, protocol, name, stype,
                    domain, avahi.PROTO_UNSPEC, dbus.UInt32(0),
                    reply_handler=self.resolved, error_handler=self.resolve_error)

    def item_remove(self, interface, protocol, name, service, domain, flags):
        name = unicode(name)

        logging.debug("service removed. interface: %s, protocol: %s, name: %s, service: %s, domain: %s", interface, protocol, name, service, domain)
        if name in self.services:
            info = self.services.pop(name)
            self.emit('service-down', name, info)

    def all_for_now(self):
        logging.debug("all for now")

    def resolve_error(self, *args, **kwargs):
        with self.lock:
            logging.error("Resolve error: %s %s", args, kwargs)


if __name__ == '__main__':
    def on_new_service(browser, name, info):
        print 'New MBC service discovered: ', name
        print 'Info: ', info

    browser = MBCZeroconfBrowser()
    browser.connect('service-up', on_new_service)
    loop = GLib.MainLoop()
    loop.run()

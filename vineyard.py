#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys, os, shutil
import uuid
import re
import json
from string import Template

from gi.repository import GLib, GObject, Gtk, WebKit, JSCore, Soup
from xdg.BaseDirectory import xdg_cache_home

from mbczcbrowse import MBCZeroconfBrowser

class Vineyard(GObject.GObject):
    def __init__(self):
        GObject.GObject.__init__(self)
        self.window = window = Gtk.Window()
        self.inspectorWindow = Gtk.Window()
        self.session = WebKit.get_default_session()
        self.zcbrowser = MBCZeroconfBrowser()

        self.services = {}
        self.zcbrowser.connect('service-up', self.on_new_service)
        self.zcbrowser.connect('service-down', self.on_service_removed)

        self.webView = webView = WebKit.WebView()
        window.add(webView)
        window.set_decorated(False)
        window.set_title('MBC - Vineyard')

        self.init_settings()
        self.add_inspector()
        self.add_cookie_jar()

        webView.connect ("navigation-policy-decision-requested", self.decide_policy_cb)
        webView.connect ("close-web-view", lambda app: Gtk.main_quit())
        webView.connect ("load-error", self.load_error_cb)
        webView.connect ("document-load-finished", self.load_finished_cb)
        webView.connect ("window-object-cleared", self.window_object_cleared_cb)
        webView.set_property ("view-mode", WebKit.WebViewViewMode.FULLSCREEN)

        window.connect ("destroy", lambda app: Gtk.main_quit())
        window.show_all ()
        window.fullscreen ()

        webView.grab_focus()
        # replace this with magic.
        webView.load_uri('http://localhost:3000/')

    def init_settings(self):
        settings = self.webView.get_settings()
        for prop in 'enable-accelerated-compositing enable-fullscreen enable-webgl enable-developer-extras'.split(' '):
            settings.set_property(prop, True)

    def decide_policy_cb (self, view, frame, request, action, decision, data=None):
        # just a placeholder for now, but will be handy to have custom urls, like
        # mbc://something
        # Also, perhaps writing a custom libsoup handler would be better on the long term.
        uri = request.get_uri()
        scheme, path=uri.split(':', 1)
        if scheme != 'mbc':
            # Will use the default behaviour.
            return False

        # a dummy example.
        path = re.sub('^//', '', path)
        if re.match('^quit/?$', 'quit'):
            Gtk.main_quit()

        # To stop further processing.
        return True

    def window_object_cleared_cb (self, view, frame, context, window_object, data=None):
        # we can inject custom stuff either executing some js or touching the context.
        vinejs = Template("""
            window.Vineyard = {
                services: $services,
                onServiceAdded: function(serviceName, serviceInfo){},
                onServiceRemoved: function(serviceName, serviceInfo){},
            };
        """).substitute(services=json.dumps(self.services))
        view.execute_script (vinejs)

    def load_finished_cb (self, view, frame, data=None):
        pass

    def load_error_cb (self, view, frame, uri, error, data=None):
        pass

    def add_inspector(self):
        def create_inspector_window(inspector, srcwebview, data=None):
            webview = WebKit.WebView()
            self.inspectorWindow.add(webview)
            return webview

        def show_inspector_window(inspector, data=None):
            self.inspectorWindow.show()

        inspector = self.webView.get_inspector()
        inspector.connect('inspect-web-view', create_inspector_window)
        inspector.connect('show-window', show_inspector_window)

    def add_cookie_jar(self):
        # here we store everything, however it would be best not to do it
        # if we care about not leaving auth stuff around.
        cookiejar = Soup.CookieJarText.new( os.path.join(xdg_cache_home, "vineyard_cookies.txt"), False)
        cookiejar.set_accept_policy(Soup.CookieJarAcceptPolicy.ALWAYS)
        self.session.add_feature(cookiejar)

    #ZeroConf callbacks.
    def on_new_service(self, browser, name, info):
        self.services[name] = info

        name = json.dumps(name)
        info = json.dumps(info)

        vinejs = Template(u"""
        (function(){
            if (window.Vineyard) {
                window.Vineyard.services[$name] = $info;
                window.Vineyard.onServiceAdded($name, $info);
            }
        })();
        """).substitute(name=name, info=info)
        self.webView.execute_script (vinejs)

    def on_service_removed(self, browser, name, info):
        info = self.services.pop(name, None)
        if info is None:
            return

        name = json.dumps(name)
        info = json.dumps(info)

        vinejs = Template(u"""
        (function(){
            if (window.Vineyard) {
                delete window.Vineyard.services[$name];
                window.Vineyard.onServiceRemoved($name, $info);
            }
        })();
        """).substitute(name=name, info=info)
        self.webView.execute_script (vinejs)


if __name__ == '__main__':
    app = Vineyard()

    Gtk.main()

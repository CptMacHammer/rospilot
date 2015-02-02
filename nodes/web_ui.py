#!/usr/bin/env python

'''
Copyright 2012 the original author or authors.
See the NOTICE file distributed with this work for additional
information regarding copyright ownership.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

import roslib
roslib.load_manifest('rospilot')
import rospy
import json
import cherrypy
import os
import re
import glob
import std_srvs.srv
import rospilot.srv
import urllib2
import cv2
from optparse import OptionParser
from catkin.find_in_workspaces import find_in_workspaces

STATIC_PATH = find_in_workspaces(['share'], 'rospilot',
                                 'share/web_assets/', first_match_only=True)[0]

PORT_NUMBER = 8085


class API(object):
    def __init__(self, media_path):
        self.media_path = media_path

    @cherrypy.expose
    def media(self, id=None):
        if cherrypy.request.method == "DELETE":
            if not re.match(r"([a-z]+\.)?[a-zA-Z0-9_-]+\.\w{2,5}", id):
                rospy.logwarn("Ignoring request to delete %s", id)
                return
            os.remove(self.media_path + "/" + id)
        elif cherrypy.request.method == "GET":
            paths = os.listdir(self.media_path)
            objs = []
            for path in reversed(sorted(paths)):
                if path.endswith('jpg'):
                    objs.append({"type": "image", "url": "/media/" + path,
                                "id": path})
                else:
                    thumbnail = "/api/thumbnail?filename=" + path
                    objs.append({"type": "video", "url": "/media/" + path,
                                 "thumbnail": thumbnail,
                                 "id": path})
            return json.dumps(objs)

    @cherrypy.expose
    def thumbnail(self, filename):
        cap = cv2.VideoCapture(self.media_path + "/" + filename)
        ret, frame = cap.read()
        ret, jpg = cv2.imencode(".jpg", frame)
        cap.release()
        cherrypy.response.headers['Content-Type'] = 'image/jpeg'
        return jpg.tostring()

    @cherrypy.expose
    def camera(self, action):
        url = 'http://localhost:8080/snapshot?topic=/camera/image_raw/compressed'
        resp = urllib2.urlopen(url)
        cherrypy.response.headers['Content-Type'] = resp.info()['Content-Type']
        return resp.read()


class Index(object):
    @cherrypy.expose
    def index(self):
        return open(os.path.join(STATIC_PATH, "index.html")).read()


class WebUiNode(object):
    def __init__(self, media_path):
        rospy.Service('glob',
                      rospilot.srv.Glob,
                      self.handle_glob)
        rospy.Service('shutdown',
                      std_srvs.srv.Empty,
                      self.handle_shutdown)
        self.media_path = os.path.expanduser(media_path)
        if not os.path.exists(self.media_path):
            os.makedirs(self.media_path)

        cherrypy.server.socket_port = PORT_NUMBER
        cherrypy.server.socket_host = '0.0.0.0'
        # No autoreloading
        cherrypy.engine.autoreload.unsubscribe()
        conf = {
            '/static': {'tools.staticdir.on': True,
                        'tools.staticdir.dir': STATIC_PATH
                        },
            '/media': {'tools.staticdir.on': True,
                       'tools.staticdir.dir': self.media_path
                       }
        }
        index = Index()
        index.api = API(self.media_path)
        cherrypy.tree.mount(index, config=conf)
        cherrypy.log.screen = False

    def handle_glob(self, request):
        return rospilot.srv.GlobResponse(glob.glob(request.pattern))

    def handle_shutdown(self, request):
        os.system('shutdown now -P')
        return std_srvs.srv.EmptyResponse()

    def run(self):
        rospy.init_node('rospilot_webui')
        rospy.loginfo("Web UI is running")
        cherrypy.engine.start()
        rospy.spin()
        cherrypy.engine.exit()

if __name__ == '__main__':
    parser = OptionParser("web_ui.py <options>")
    parser.add_option(
        "--media_path",
        dest="media_path",
        type='string',
        help="Directory to store media generated by drone",
        default="/tmp")
    (opts, args) = parser.parse_args()

    node = WebUiNode(media_path=opts.media_path)
    node.run()

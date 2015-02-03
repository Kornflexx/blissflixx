#!/usr/bin/python
from os import path
import sys, os
LIB_PATH = path.join(path.abspath(path.dirname(__file__)), "lib")
sys.path.append(LIB_PATH)
import locations, gitutils
sys.path.append(locations.EXTN_PATH)
sys.path.append(locations.YTUBE_PATH)

# Make sure we have youtube-dl
if not path.exists(locations.EXTN_PATH):
  os.makedirs(locations.EXTN_PATH)
if not path.exists(locations.YTUBE_PATH):
  print ("Installing youtube-dl. Please wait...")
  gitutils.clone(locations.EXTN_PATH,"https://github.com/rg3/youtube-dl.git")

import cherrypy, json, shutil, subprocess
import signal, traceback, argparse
from cherrypy.process.plugins import Daemonizer
import player, api

class Html(object): pass

class Api(object):

  def _error(self, status, msg):
    cherrypy.response.status = status
    return {'error': msg}

  def _server(self, fn=None, data=None):
    if fn == 'restart':
      gitutils.pull_subdirs(locations.EXTN_PATH)
      gitutils.pull(locations.ROOT_PATH)
      os.kill(os.getpid(), signal.SIGUSR2)
    else:
      return self._error(404, "API Function '" + fn + "' is not defined")

  @cherrypy.expose
  def chanimage(self, chid, img):
    path = os.path.join(locations.CHAN_PATH, chid, img)
    return cherrypy.lib.static.serve_file(path)

  @cherrypy.expose
  @cherrypy.tools.json_out()
  def default(self, modname, fn=None, data=None):
    if modname == 'server':
      return self._server(fn, data)
    module = getattr(api, modname)
    if module is None:
      return self._error(404, "API Module '" + modname + "' is not defined")
    call = getattr(module, fn)
    if call is None:
      return self._error(404, "API Function '" + fn + "' is not defined")
    if data is not None:
      datadict = json.loads(data)
    else:
      datadict = {}
    try:
      ret = call(**datadict)
      if ret is not None:
        return ret
    except Exception, e:
      return self._error(500, traceback.format_exc())

def cleanup():
  # Cleanup if previously crashed or was killed
  try:
    shutil.rmtree('/tmp/torrent-stream')
  except Exception:
    pass
  try:
    shutil.rmtree('/tmp/blissflixx')
  except Exception:
    pass
  try:
    home = os.path.expanduser("~")
    os.remove(home + "/.swfinfo")
  except Exception:
    pass
  kill_process("omxplayer")
  kill_process("peerflix")

def kill_process(name):
  s = subprocess.check_output("ps -ef | grep " + name, shell=True)
  lines = s.split('\n')
  for l in lines:
    items = l.split()
      # Don't kill our own command
    if len(items) > 2 and l.find("grep " + name) == -1:
      try:
        os.kill(int(items[1]), signal.SIGTERM)
      except Exception:
        pass

def create_data_dir():
  datapath = locations.DATA_PATH
  playlists = os.path.join(datapath, "playlists")
  settings = os.path.join(datapath, "settings")
  if not os.path.exists(datapath):
    os.makedirs(datapath)
  if not os.path.exists(playlists):
    os.makedirs(playlists)
  if not os.path.exists(settings):
    os.makedirs(settings)


parser = argparse.ArgumentParser()
parser.add_argument("--daemon", help="Run as daemon process", 
                    action="store_true")
parser.add_argument("--port", type=int, help="Listen port (default 6969)")
args = parser.parse_args()

engine = cherrypy.engine
if args.daemon:
  Daemonizer(engine).subscribe()

cleanup()
create_data_dir()

cherrypy.tree.mount(Api(), '/api')
cherrypy.tree.mount(Html(), '/', config = {
  '/': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': locations.HTML_PATH,
          'tools.staticdir.index': 'index.html',
    },
  })

engine.signal_handler.handlers['SIGINT'] = engine.signal_handler.bus.exit
engine.signal_handler.handlers['SIGUSR2'] = engine.signal_handler.bus.restart
cherrypy.config.update({'server.socket_host': '0.0.0.0'})
port = 6969
if args.port:
  port = args.port
cherrypy.config.update({'server.socket_port': port})
cherrypy.config.update({'engine.autoreload.on': False})
cherrypy.config.update({'checker.check_skipped_app_config': False})
engine.signals.subscribe()
engine.start()
player.start_thread()
engine.block()

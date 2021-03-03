import os
import re
from flask_socketio import SocketIO, emit, join_room, leave_room, send
from flask import Flask, render_template, request, session, redirect, url_for, Session
import json
import time
from datetime import datetime

from threading import Thread, Event
from random import random


# Initialise and configure flask application
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY')


# Initialise SocketIO
#socketio = SocketIO(app);
socketio = SocketIO(app, cors_allowed_origins="*")

block_some_templates = False


###################### WORKER ##########################

@app.route("/worker")
def worker():
  
  if(block_some_templates):
     return "blocked by admin"

  return render_template('worker.html',)


class DataPacket:
     def __init__(self):
         self.data = dict()
         self.history = dict()
         self.utc = list()
         self.length_history = 5;
         self.id_session = str(datetime.utcnow())

     def push(self, packet):

         list_key_remove = packet['D']
         for key in list_key_remove:
             self.data.pop(key, None)

         data_modify = packet['M']
         for key in data_modify:
             self.data[key] = data_modify[key] 

         new_data = packet['N']
         for key in new_data:
             self.data[key] = new_data[key]

         print("____________")
         print("dato")
         print(self.data)
         print("paquete")
         print(packet)
         print("____________")

         

         if(len(self.utc) < self.length_history):
            utc_now = str(datetime.utcnow())
            self.utc.append(utc_now)
            #self.history[utc_now] = packet
            self.history[utc_now] = {"D": [], "M": {}, "N": {}}
         else:
            utc_rm = self.utc[0]
            self.history.pop(utc_rm)
            utc_now = str(datetime.utcnow())
            self.utc = self.utc[1:] + [utc_now]   
            #self.history[utc_now] = packet
            self.history[utc_now] = {"D": [], "M": {}, "N": {}}
                  
          
         for t in self.utc[:-1]:
              self.update(self.history[t], packet)

         print("history:")
         print(self.history)

     def update(self, previous_packet, actual_packet):

         list_d = list()
         for i, key in enumerate(actual_packet['D']):
             if(key in previous_packet['M']):
                previous_packet['M'].pop(key)
             elif(key in previous_packet['N']):
                previous_packet['N'].pop(key)
             else:
                list_d.append(key)

         previous_packet['D'] = list(set(previous_packet['D']) | set(list_d))
         
         for key in actual_packet['M']:
             previous_packet['M'][key] = actual_packet['M'][key]
             if(key in previous_packet['N']):
                 previous_packet['N'].pop(key)

         for key in actual_packet['N']:
             previous_packet['N'][key] = actual_packet['N'][key]


     def get_utc_now(self):
         print("____get utc______")
         print(id(self.utc))
         print(self.utc)
         print("data")
         print(self.data)
         if(len(self.utc) == 0):
             return '1970-01-01 00:00:00'
         else:
             return self.utc[-1]

     def reset(self):
         self.data.clear()
         self.history.clear()
         self.utc.clear()
         self.id_session = str(datetime.utcnow())


dataPacket = DataPacket()

@socketio.on('connect', namespace = '/worker')
def worker_connect():
        global dataPacket
        print('worker conectado')
        dataPacket.reset()
        emit('start', {'data': 'Connected'}, namespace = '/worker')


@socketio.on('new_data', namespace = '/worker')
def worker_data(packet):
        global dataPacket
        print("actual dato antes de push")
        print(dataPacket.data)
        dataPacket.push(packet)
        emit('update', {'utc': dataPacket.get_utc_now()}, namespace = '/map', broadcast=True)
        #we send utc data to the parking lot user, but in this implementation the parking lot user does not use it
        emit('update', {'utc': dataPacket.get_utc_now()}, namespace = '/parkingLot', broadcast=True)

@socketio.on('reset', namespace = '/worker')
def worker_reset(json_data):
        global dataPacket
        print('reset')
        dataPacket.reset()
        emit('start', {'data': json_data}, namespace = '/worker')

       


@socketio.on('disconnect', namespace = '/worker')
def worker_disconnect():
        print('Client disconnected')


####################### MAP ############################

#befor url was "index_map"
@app.route("/")
def map():
  return render_template('map2.html',)


@socketio.on('connect', namespace = '/map')
def map_connect():
        print('map user connected') 

        #_______________for testing___________________
        #this trick (broadcast=True) works because only there is one worker for this implementation
        emit('newMapUser', {'msg': "new map user"}, namespace = '/worker', broadcast=True)
        #_____________________________________________

        emit('update', {'utc': dataPacket.get_utc_now()}, namespace = '/map')

@socketio.on('get_data', namespace = '/map')
def map_connect(data_user):
        print('____get data__')
        print("dato actual")
        print(dataPacket.data)

        if(data_user['id_session'] != dataPacket.id_session):
          print("c1: enviar dato completo, id_session diferente")
          emit('new_data', {'data': dataPacket.data, 'R': True, 'utc': dataPacket.get_utc_now(), 'id_session': dataPacket.id_session}, namespace = '/map')
        else:
            if(data_user['utc'] in dataPacket.history):
                print("c2")
                print("utc recibido")
                print(data_user['utc'])
                emit('new_data', {'data': dataPacket.history[data_user['utc']], 'R': False, 'utc': dataPacket.get_utc_now(), 'id_session': dataPacket.id_session}, namespace = '/map')
            else:
                print("c3: enviar dato completo, no hay historico")
                emit('new_data', {'data': dataPacket.data, 'R': True, 'utc': dataPacket.get_utc_now(), 'id_session': dataPacket.id_session}, namespace = '/map')



@socketio.on('disconnect', namespace = '/map')
def map_disconnect():
        print('map disconnected')



################## PARKING LOT USER ##################

@socketio.on('connect', namespace = '/parkingLot')
def worker_connect():
        print('parking lot user connected')
        emit('start', {'data': 'Connected'}, namespace = '/parkingLot')


@socketio.on('get_state', namespace = '/parkingLot')
def get_state(json_data):
        print('get state')
        print(json_data)
        dataParkingLot = dict()
        for index in json_data:
            key = str(index)
            if key in dataPacket.data:
              dataParkingLot[index] = dataPacket.data[key]
        emit('updateParkingLots', {'data': dataParkingLot}, namespace = '/parkingLot')


@socketio.on('update_worker', namespace = '/parkingLot')
def update_worker(json_data):
        print('update_worker')
        print(json_data)
        #this trick (broadcast=True) works because only there is one worker for this implementation
        emit('updateWorker', {'data': json_data}, namespace = '/worker', broadcast=True)


@socketio.on('disconnect', namespace = '/parkingLot')
def map_disconnect():
        print('parking lot user disconnected')


@app.route("/parking_lot_user")
def parkingLotUser():

  if(block_some_templates):
     return "blocked by admin"

  return render_template('parking_lot_user.html',)




if __name__ == "__main__":
  socketio.run(app)


















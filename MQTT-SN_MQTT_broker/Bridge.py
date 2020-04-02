"""
/*******************************************************************************
 * Copyright (c) 2011, 2013 IBM Corp.
 *
 * All rights reserved. This program and the accompanying materials
 * are made available under the terms of the Eclipse Public License v1.0
 * and Eclipse Distribution License v1.0 which accompany this distribution. 
 *
 * The Eclipse Public License is available at 
 *    http://www.eclipse.org/legal/epl-v10.html
 * and the Eclipse Distribution License is available at 
 *   http://www.eclipse.org/org/documents/edl-v10.php.
 *
 * Contributors:
 *    Ian Craggs - initial API and implementation and/or initial documentation
 *******************************************************************************/
"""
import paho.mqtt.client as paho 
import os
import json
import time 
import random
from datetime import datetime 
import MQTTSN, socket, time, MQTTSNinternal, thread, types, sys, struct


class Callback:

  def __init__(self):
    self.events = []
    self.registered = {}
    self.payload = None

  def connectionLost(self, cause):
    print "default connectionLost", cause
    self.events.append("disconnected")

  def messageArrived(self, topicName, payload, qos, retained, msgid):
    print "default publishArrived", topicName, payload, qos, retained, msgid
    self.payload = payload
    return True

  def deliveryComplete(self, msgid):
    print "default deliveryComplete"
  
  def advertise(self, address, gwid, duration):
    print "advertise", address, gwid, duration

  def register(self, topicid, topicName):
    self.registered[topicId] = topicName


class Client:

  def __init__(self, clientid, host="localhost", port=1883):
    self.clientid = clientid
    self.host = host
    self.port = port
    self.msgid = 1
    self.callback = None
    self.__receiver = None
    
  def start(self):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.bind((self.host, self.port))
    mreq = struct.pack("4sl", socket.inet_aton(self.host), socket.INADDR_ANY)

    self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    
    self.startReceiver()
      
  def stop(self):
    self.stopReceiver()

  def __nextMsgid(self):
    def getWrappedMsgid():
      id = self.msgid + 1
      if id == 65535:
        id = 1
      return id

    if len(self.__receiver.outMsgs) >= 65535:
      raise "No slots left!!"
    else:
      self.msgid = getWrappedMsgid()
      while self.__receiver.outMsgs.has_key(self.msgid):
        self.msgid = getWrappedMsgid()
    return self.msgid


  def registerCallback(self, callback):
    self.callback = callback


  def connect(self, cleansession=True):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #self.sock.settimeout(5.0)

    self.sock.connect((self.host, self.port))

    connect = MQTTSN.Connects()
    connect.ClientId = self.clientid
    connect.CleanSession = cleansession
    connect.KeepAliveTimer = 0
    self.sock.send(connect.pack())

    response, address = MQTTSN.unpackPacket(MQTTSN.getPacket(self.sock))
    assert response.mh.MsgType == MQTTSN.CONNACK
    
    self.startReceiver()

    
  def startReceiver(self):
    self.__receiver = MQTTSNinternal.Receivers(self.sock)
    if self.callback:
      id = thread.start_new_thread(self.__receiver, (self.callback,))


  def waitfor(self, msgType, msgId=None):
    if self.__receiver:
      msg = self.__receiver.waitfor(msgType, msgId)
    else:
      msg = self.__receiver.receive()
      while msg.mh.MsgType != msgType and (msgId == None or msgId == msg.MsgId):
        msg = self.__receiver.receive()
    return msg


  def subscribe(self, topic, qos=2):
    subscribe = MQTTSN.Subscribes()
    subscribe.MsgId = self.__nextMsgid()
    if type(topic) == types.StringType:
      subscribe.TopicName = topic
      if len(topic) > 2:
        subscribe.Flags.TopicIdType = MQTTSN.TOPIC_NORMAL
      else:
        subscribe.Flags.TopicIdType = MQTTSN.TOPIC_SHORTNAME
    else:
      subscribe.TopicId = topic # should be int
      subscribe.Flags.TopicIdType = MQTTSN.TOPIC_PREDEFINED
    subscribe.Flags.QoS = qos
    if self.__receiver:
      self.__receiver.lookfor(MQTTSN.SUBACK)
    self.sock.send(subscribe.pack())
    msg = self.waitfor(MQTTSN.SUBACK, subscribe.MsgId)
    return msg.ReturnCode, msg.TopicId


  def unsubscribe(self, topics):
    unsubscribe = MQTTSN.Unsubscribes()
    unsubscribe.MsgId = self.__nextMsgid()
    unsubscribe.data = topics
    if self.__receiver:
      self.__receiver.lookfor(MQTTSN.UNSUBACK)
    self.sock.send(unsubscribe.pack())
    msg = self.waitfor(MQTTSN.UNSUBACK, unsubscribe.MsgId)
  
  
  def register(self, topicName):
    register = MQTTSN.Registers()
    register.TopicName = topicName
    if self.__receiver:
      self.__receiver.lookfor(MQTTSN.REGACK)
    self.sock.send(register.pack())
    msg = self.waitfor(MQTTSN.REGACK, register.MsgId)
    return msg.TopicId


  def publish(self, topic, payload, qos=0, retained=False):
    publish = MQTTSN.Publishes()
    publish.Flags.QoS = qos
    publish.Flags.Retain = retained
    if type(topic) == types.StringType:
      publish.Flags.TopicIdType = MQTTSN.TOPIC_SHORTNAME
      publish.TopicName = topic
    else:
      publish.Flags.TopicIdType = MQTTSN.TOPIC_NORMAL
      publish.TopicId = topic
    if qos in [-1, 0]:
      publish.MsgId = 0
    else:
      publish.MsgId = self.__nextMsgid()
      print "MsgId", publish.MsgId
      self.__receiver.outMsgs[publish.MsgId] = publish
    publish.Data = payload
    self.sock.send(publish.pack())
    return publish.MsgId
  

  def disconnect(self):
    disconnect = MQTTSN.Disconnects()
    if self.__receiver:
      self.__receiver.lookfor(MQTTSN.DISCONNECT)
    self.sock.send(disconnect.pack())
    msg = self.waitfor(MQTTSN.DISCONNECT)
    

  def stopReceiver(self):
    self.sock.close() # this will stop the receiver too
    assert self.__receiver.inMsgs == {}
    assert self.__receiver.outMsgs == {}
    self.__receiver = None

  def receive(self):
    return self.__receiver.receive()


def publish(topic, payload, retained=False, port=1883, host="localhost"):
  publish = MQTTSN.Publishes()
  publish.Flags.QoS = 3
  publish.Flags.Retain = retained  
  if type(topic) == types.StringType:
    if len(topic) > 2:
      publish.Flags.TopicIdType = MQTTSN.TOPIC_NORMAL
      publish.TopicId = len(topic)
      payload = topic + payload
    else:
      publish.Flags.TopicIdType = MQTTSN.TOPIC_SHORTNAME
      publish.TopicName = topic
  else:
    publish.Flags.TopicIdType = MQTTSN.TOPIC_NORMAL
    publish.TopicId = topic
  publish.MsgId = 0
  print "payload", payload
  publish.Data = payload
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.sendto(publish.pack(), (host, port))
  sock.close()
  return 

"""
if __name__ == "__main__":
  
	
  mclient = Client("myclientid", host="225.0.18.83", port=1883)
  mclient.registerCallback(Callback())
  mclient.start()
  
  publish("long topic name", "qos -1 start", port=1884)

  callback = Callback()

  aclient = Client("myclientid", port=1884)
  aclient.registerCallback(callback)

  aclient.connect()
  aclient.disconnect()

  aclient.connect()
  aclient.subscribe("k ", 2)
  aclient.subscribe("jkjkjkjkj", 2)
  aclient.publish("k ", "qos 0")
  aclient.publish("k ", "qos 1", 1)
  aclient.publish("jkjkjkjkj", "qos 2", 2)
  topicid = aclient.register("jkjkjkjkj")
  #time.sleep(1.0)
  aclient.publish(topicid, "qos 2 - registered topic id", 2)
  #time.sleep(1.0)
  aclient.disconnect()
  publish("long topic name", "qos -1 end", port=1884)
  
  time.sleep(30)
  mclient.stop()
	"""

#Settings to connect to ThingsBoard devices

#Devices' access tokens 
ACCESS_TOKEN_TEMPERATURE_ES_1 = 'LuzNyU3GMUx5wjOGgRsK'
ACCESS_TOKEN_TEMPERATURE_ES_2 = 'NvN9S2mtXhLEdPsFBMp3'

ACCESS_TOKEN_HUMIDITY_ES_1 = 'AO0xdeod7Rb9iG4PWWRf'
ACCESS_TOKEN_HUMIDITY_ES_2 = 'VFhoX1D9XPhfFCDcRvjy'

ACCESS_TOKEN_WIND_DIRECTION_ES_1 = '1LX2hYd7jFJzMgnIiCtv'
ACCESS_TOKEN_WIND_DIRECTION_ES_2 = '4j4n4zSnY7FR5INLgtLm'

ACCESS_TOKEN_WIND_INTENSITY_ES_1 = 'yJI4iC83pIAj6zCGNaVT'
ACCESS_TOKEN_WIND_INTENSITY_ES_2 = 'DBcsnpeitI52ubslZgJY'

ACCESS_TOKEN_RAIN_HEIGHT_ES_1 = '5l4srhQKSd7SHsnL2DhK'
ACCESS_TOKEN_RAIN_HEIGHT_ES_2 = 'vFcwHdKJoF3qtkT6xwsc'

#Connect to ThingsBoard
thingsboard_host = "demo.thingsboard.io"
thingsboard_topic = "v1/devices/me/telemetry"
thingsboard_port = 1883

#Connect to Mosquitto MQTT-SN broker
mosquitto_port = 1885

#Mosquitto topics (these must be the arguments passed to the RIOT program for everything to work)
mosquittoTopic_temperature_1 = "tmp1"
mosquittoTopic_temperature_2 = "tmp2"

mosquittoTopic_humidity_1 = "hum1"
mosquittoTopic_humidity_2 = "hum2"

mosquittoTopic_windDirection_1 = "wdir1"
mosquittoTopic_windDirection_2 = "wdir2"

mosquittoTopic_windIntensity_1 = "wint1" 
mosquittoTopic_windIntensity_2 = "wint2"

mosquittoTopic_rainHeight_1 = "rnhgt1"
mosquittoTopic_rainHeight_2 = "rnhgt2"

#Data published
def dataPublished(client, userdata, result):
  print ("Data successfully published on ThingsBoard\n")
  pass

def connectedThingsBoard():
  print ("Connected to ThingsBoard device")
  pass

#Connect client function
def connectThingsBoardClient(clientName, deviceAccessToken):
  TS_client = paho.Client(clientName)
  TS_client.on_connect = connectedThingsBoard()
  TS_client.on_publish = dataPublished
  TS_client.username_pw_set(deviceAccessToken)
  TS_client.connect(thingsboard_host, thingsboard_port, keepalive=60)
  return TS_client

#Collect data from Mosquitto MQTT-SN broker
def takeData(mosquittoClient, mosquittoTopic):
  mosquittoClient.registerCallback(Callback())
  mosquittoClient.connect()
  print("Connected\n")
  rc, topic = mosquittoClient.subscribe(mosquittoTopic)
  
def sendData(clientName, mosquittoClient):
  clientName.publish(thingsboard_topic, mosquittoClient.callback.payload)
  print(mosquittoClient.callback.payload)
  print("\n\n")

#Connect to ThingsBoard's devices
clientTemperature_1 = connectThingsBoardClient("Temperature Device ES-1", ACCESS_TOKEN_TEMPERATURE_ES_1)
clientTemperature_2 = connectThingsBoardClient("Temperature Device ES-2", ACCESS_TOKEN_TEMPERATURE_ES_2)

clientHumidity_1 = connectThingsBoardClient("Humidity Device ES-1", ACCESS_TOKEN_HUMIDITY_ES_1)
clientHumidity_2 = connectThingsBoardClient("Humidity Device ES-2", ACCESS_TOKEN_HUMIDITY_ES_2)

clientWindDirection_1 = connectThingsBoardClient("Wind Direction Device ES-1", ACCESS_TOKEN_WIND_DIRECTION_ES_1)
clientWindDirection_2 = connectThingsBoardClient("Wind Direction Device ES-2", ACCESS_TOKEN_WIND_DIRECTION_ES_2)

clientWindIntensity_1 = connectThingsBoardClient("Wind Intensity Device ES-1", ACCESS_TOKEN_WIND_INTENSITY_ES_1)
clientWindIntensity_2 = connectThingsBoardClient("Wind Intensity Device ES-2", ACCESS_TOKEN_WIND_INTENSITY_ES_2)

clientRainHeight_1 = connectThingsBoardClient("Rain Heigth Device ES-1", ACCESS_TOKEN_RAIN_HEIGHT_ES_1)
clientRainHeight_2 = connectThingsBoardClient("Rain Height Device ES-2", ACCESS_TOKEN_RAIN_HEIGHT_ES_2)

#Start devices' threads
clientTemperature_1.loop_start()
clientTemperature_2.loop_start()

clientHumidity_1.loop_start()
clientHumidity_2.loop_start()

clientWindDirection_1.loop_start()
clientWindDirection_2.loop_start()

clientWindIntensity_1.loop_start()
clientWindIntensity_2.loop_start()

clientRainHeight_1.loop_start()
clientRainHeight_2.loop_start()

#Mosquitto clients
mosquittoClient_temperature_1 = Client("MQTT-SN Temperature ES-1", port=mosquitto_port)
mosquittoClient_temperature_2 = Client("MQTT-SN Temperature ES-2", port=mosquitto_port)

mosquittoClient_humidity_1 = Client("MQTT-SN Humidity ES-1", port=mosquitto_port)
mosquittoClient_humidity_2 = Client("MQTT-SN Humidity ES-2", port=mosquitto_port)

mosquittoClient_windDirection_1 = Client("MQTT-SN Wind Direction ES-1", port=mosquitto_port)
mosquittoClient_windDirection_2 = Client("MQTT-SN Wind Direction ES-2", port=mosquitto_port)

mosquittoClient_windIntensity_1 = Client("MQTT-SN Wind Intensity ES-1", port=mosquitto_port)
mosquittoClient_windIntensity_2 = Client("MQTT-SN Wind Intensity ES-2", port=mosquitto_port)

mosquittoClient_rainHeight_1 = Client("MQTT-SN Rain Height ES-1", port=mosquitto_port)
mosquittoClient_rainHeight_2 = Client("MQTT-SN Rain Height ES-2", port=mosquitto_port)

while(True):
  
  #Collect data from Mosquitto broker
  takeData(mosquittoClient_temperature_1, mosquittoTopic_temperature_1)
  takeData(mosquittoClient_temperature_2, mosquittoTopic_temperature_2)
  
  takeData(mosquittoClient_humidity_1, mosquittoTopic_humidity_1)
  takeData(mosquittoClient_humidity_2, mosquittoTopic_humidity_2)

  takeData(mosquittoClient_windDirection_1, mosquittoTopic_windDirection_1)
  takeData(mosquittoClient_windDirection_2, mosquittoTopic_windDirection_2)
  
  takeData(mosquittoClient_windIntensity_1, mosquittoTopic_windIntensity_1)
  takeData(mosquittoClient_windIntensity_2, mosquittoTopic_windIntensity_2)
    
  takeData(mosquittoClient_rainHeight_1, mosquittoTopic_rainHeight_1)
  takeData(mosquittoClient_rainHeight_2, mosquittoTopic_rainHeight_2)
  
  
  
  '''
  !!!!! QUESTO FUNZIONA !!!!!!!!
  mosquittoClient_temperature_1.registerCallback(Callback())
  mosquittoClient_temperature_1.connect()
  rc, topic1 = mosquittoClient_temperature_1.subscribe("tmp1")
  !!!!!!!!!!!!!!!!!!!!!!
  
  

  takeData(mosquittoClient_temperature_1, mosquittoTopic_temperature_1)
  '''
  #Check data
  while(mosquittoClient_temperature_1.callback.payload == None or 
        mosquittoClient_temperature_2.callback.payload == None or 
        mosquittoClient_humidity_1.callback.payload == None or
        mosquittoClient_humidity_2.callback.payload == None or
        mosquittoClient_windDirection_1.callback.payload == None or
        mosquittoClient_windDirection_2.callback.payload == None or
        mosquittoClient_windIntensity_1.callback.payload == None or
        mosquittoClient_windIntensity_2.callback.payload == None or 
        mosquittoClient_rainHeight_1.callback.payload == None or 
        mosquittoClient_rainHeight_2.callback.payload == None):
    pass
    '''
  while(mosquittoClient_temperature_1.callback.payload == None):
    pass
  '''
  #Send data to ThingsBoard

  sendData(clientTemperature_1, mosquittoClient_temperature_1)
  sendData(clientTemperature_2, mosquittoClient_temperature_2)
  
  sendData(clientHumidity_1, mosquittoClient_humidity_1)
  sendData(clientHumidity_2, mosquittoClient_humidity_2)

  sendData(clientWindDirection_1, mosquittoClient_windDirection_1)
  sendData(clientWindDirection_2, mosquittoClient_windDirection_2)
  
  sendData(clientWindIntensity_1, mosquittoClient_windIntensity_1)
  sendData(clientWindIntensity_2, mosquittoClient_windIntensity_2)
  
  sendData(clientRainHeight_1, mosquittoClient_rainHeight_1)
  sendData(clientRainHeight_2, mosquittoClient_rainHeight_2)
  
  #Disconnect Mosquitto clients when no longer needed
  mosquittoClient_temperature_1.disconnect()
  mosquittoClient_temperature_2.disconnect()
  
  mosquittoClient_humidity_1.disconnect()
  mosquittoClient_humidity_2.disconnect()

  mosquittoClient_windDirection_1.disconnect()
  mosquittoClient_windDirection_2.disconnect()
  
  mosquittoClient_windIntensity_1.disconnect()
  mosquittoClient_windIntensity_2.disconnect()
    
  mosquittoClient_rainHeight_1.disconnect()
  mosquittoClient_rainHeight_2.disconnect()


  
"""
	aclient = Client("linh", port=1885)
	aclient.registerCallback(Callback())
	aclient.connect()

	rc, topic1 = aclient.subscribe("topic1")
	print "topic id for topic1 is", topic1
	rc, topic2 = aclient.subscribe("topic2")
	print "topic id for topic2 is", topic2
	aclient.publish(topic1, "aaaa", qos=0)
	aclient.publish(topic2, "bbbb", qos=0)
	aclient.unsubscribe("topic1")
	aclient.publish(topic2, "bbbb", qos=0)
	aclient.publish(topic1, "aaaa", qos=0)
	aclient.disconnect()
  """       


  
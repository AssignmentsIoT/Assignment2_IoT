# Assignmet2_IoT

Hi everyone! This is the repository I'll use to keep all the code related to the second assignent of my IoT course at Sapienza.
You can find a detailed **tutorial** in the article I posted **on Hackster.io**: https://www.hackster.io/silvia-del-piano/environmental-stations-monitoring-system-with-mqtt-broker-8f755c .<br/>
To see everything in action check the **video** I posted **on Youtube**: https://www.youtube.com/watch?v=JK9cNhD_iBc.<br/>
This work comes directly after the first assignment, so I suggest you have a look at my corresponding repo before.<br/>
## Main idea
In a few words we want to build the architecture you can see in the PDF.<br/>
We have two environmental stations. Each station has five sensors that measure different physical qualities, in particular:<br/>
- temperature ( - 50 / 50 °C)<br/>
- humidity (0 / 100 %)<br/>
- wind direction (0 / 360 °)<br/>
- wind intensity (0 / 100 m/s)<br/>
- rain height (0 / 50 mm/h)<br/>
The environmental stations will send data to a broker using MQTT-SN protocol. We have a Python bridge that has subscribed to the topics that represent the various telemetries, so that the data automatically arrives, and that forwards the messages to ThingsBoard IoT Platform. We'll be able to visualize the data on the dashboard we build in the first assignment (this is the corresponding link: https://demo.thingsboard.io/dashboards/8f004420-6dbc-11ea-8e0a-7d0ef2a682d3).<br/>
## Implementation
The sensors are simulated by the program done with RIOT OS in the Fake_RIOT_devices directory.<br/>
The MQTT-SN broker is done using Mosquitto RSMB: https://github.com/eclipse/mosquitto.rsmb.<br/>
The bridge was implemented with Python.<br/>
All the details on how to implement it and make it work are in the tutorial on Hacksteer.io.<br/>

Here you can find a [PDF report](https://github.com/AssignmentsIoT/Assignment2_IoT/blob/master/Environmental%20Station%20Monitoring%20System-1.pdf) (there is also a pptx version in the repository).

Have a nice day!

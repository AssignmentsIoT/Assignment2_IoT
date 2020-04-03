#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

#include "shell.h"
#include "msg.h"
#include "net/emcute.h"
#include "net/ipv6/addr.h"

#ifndef EMCUTE_ID
#define EMCUTE_ID           ("gertrud")
#endif
#define EMCUTE_PORT         (1883U)
#define EMCUTE_PRIO         (THREAD_PRIORITY_MAIN - 1)

#define NUMOFSUBS           (16U)
#define TOPIC_MAXLEN        (64U)

static char stack[THREAD_STACKSIZE_DEFAULT];
static msg_t queue[8];

static emcute_sub_t subscriptions[NUMOFSUBS];
static char topics[NUMOFSUBS][TOPIC_MAXLEN];

//Setting min and max value for every telemetry sensors have to measure
static float min_temperature = - 50.0;   // Celsius
static float max_temperature = 50.0;

static float min_humidity = 0.0;         // %
static float max_humidity = 100.0;

static float min_wind_direction = 0.0;    // Degrees
static float max_wind_direction = 360.0;

static float min_wind_intensity = 0.0;    // m/s
static float max_Wind_intensity = 100.0;

static float min_rain_height = 0.0;       // mm/h
static float max_rain_height = 50.0;

static void *emcute_thread(void *arg)
{
    (void)arg;
    emcute_run(EMCUTE_PORT, EMCUTE_ID);
    return NULL;    /* should never be reached */
}

static void on_pub(const emcute_topic_t *topic, void *data, size_t len)
{
    char *in = (char *)data;

    printf("### got publication for topic '%s' [%i] ###\n",
           topic->name, (int)topic->id);
    for (size_t i = 0; i < len; i++) {
        printf("%c", in[i]);
    }
    puts("");
}

static unsigned get_qos(const char *str)
{
    int qos = atoi(str);
    switch (qos) {
        case 1:     return EMCUTE_QOS_1;
        case 2:     return EMCUTE_QOS_2;
        default:    return EMCUTE_QOS_0;
    }
}

static int cmd_con(int argc, char **argv)
{
    sock_udp_ep_t gw = { .family = AF_INET6, .port = EMCUTE_PORT };
    char *topic = NULL;
    char *message = NULL;
    size_t len = 0;

    if (argc < 2) {
        printf("usage: %s <ipv6 addr> [port] [<will topic> <will message>]\n",
                argv[0]);
        return 1;
    }

    /* parse address */
    if (ipv6_addr_from_str((ipv6_addr_t *)&gw.addr.ipv6, argv[1]) == NULL) {
        printf("error parsing IPv6 address\n");
        return 1;
    }

    if (argc >= 3) {
        gw.port = atoi(argv[2]);
    }
    if (argc >= 5) {
        topic = argv[3];
        message = argv[4];
        len = strlen(message);
    }

    if (emcute_con(&gw, true, topic, message, len, 0) != EMCUTE_OK) {
        printf("error: unable to connect to [%s]:%i\n", argv[1], (int)gw.port);
        return 1;
    }
    printf("Successfully connected to gateway at [%s]:%i\n",
           argv[1], (int)gw.port);

    return 0;
}

static int cmd_discon(int argc, char **argv)
{
    (void)argc;
    (void)argv;

    int res = emcute_discon();
    if (res == EMCUTE_NOGW) {
        puts("error: not connected to any broker");
        return 1;
    }
    else if (res != EMCUTE_OK) {
        puts("error: unable to disconnect");
        return 1;
    }
    puts("Disconnect successful");
    return 0;
}

static int cmd_pub(int argc, char **argv)
{
    emcute_topic_t t;
    unsigned flags = EMCUTE_QOS_0;

    if (argc < 3) {
        printf("usage: %s <topic name> <data> [QoS level]\n", argv[0]);
        return 1;
    }

    /* parse QoS level */
    if (argc >= 4) {
        flags |= get_qos(argv[3]);
    }

    printf("pub with topic: %s and name %s and flags 0x%02x\n", argv[1], argv[2], (int)flags);

    /* step 1: get topic id */
    t.name = argv[1];
    if (emcute_reg(&t) != EMCUTE_OK) {
        puts("error: unable to obtain topic ID");
        return 1;
    }

    /* step 2: publish data */
    if (emcute_pub(&t, argv[2], strlen(argv[2]), flags) != EMCUTE_OK) {
        printf("error: unable to publish data to topic '%s [%i]'\n",
                t.name, (int)t.id);
        return 1;
    }

    printf("Published %i bytes to topic '%s [%i]'\n",
            (int)strlen(argv[2]), t.name, t.id);

    return 0;
}

static int cmd_sub(int argc, char **argv)
{
    unsigned flags = EMCUTE_QOS_0;

    if (argc < 2) {
        printf("usage: %s <topic name> [QoS level]\n", argv[0]);
        return 1;
    }

    if (strlen(argv[1]) > TOPIC_MAXLEN) {
        puts("error: topic name exceeds maximum possible size");
        return 1;
    }
    if (argc >= 3) {
        flags |= get_qos(argv[2]);
    }

    /* find empty subscription slot */
    unsigned i = 0;
    for (; (i < NUMOFSUBS) && (subscriptions[i].topic.id != 0); i++) {}
    if (i == NUMOFSUBS) {
        puts("error: no memory to store new subscriptions");
        return 1;
    }

    subscriptions[i].cb = on_pub;
    strcpy(topics[i], argv[1]);
    subscriptions[i].topic.name = topics[i];
    if (emcute_sub(&subscriptions[i], flags) != EMCUTE_OK) {
        printf("error: unable to subscribe to %s\n", argv[1]);
        return 1;
    }

    printf("Now subscribed to %s\n", argv[1]);
    return 0;
}

static int cmd_unsub(int argc, char **argv)
{
    if (argc < 2) {
        printf("usage %s <topic name>\n", argv[0]);
        return 1;
    }

    /* find subscriptions entry */
    for (unsigned i = 0; i < NUMOFSUBS; i++) {
        if (subscriptions[i].topic.name &&
            (strcmp(subscriptions[i].topic.name, argv[1]) == 0)) {
            if (emcute_unsub(&subscriptions[i]) == EMCUTE_OK) {
                memset(&subscriptions[i], 0, sizeof(emcute_sub_t));
                printf("Unsubscribed from '%s'\n", argv[1]);
            }
            else {
                printf("Unsubscription form '%s' failed\n", argv[1]);
            }
            return 0;
        }
    }

    printf("error: no subscription for topic '%s' found\n", argv[1]);
    return 1;
}

static int cmd_will(int argc, char **argv)
{
    if (argc < 3) {
        printf("usage %s <will topic name> <will message content>\n", argv[0]);
        return 1;
    }

    if (emcute_willupd_topic(argv[1], 0) != EMCUTE_OK) {
        puts("error: unable to update the last will topic");
        return 1;
    }
    if (emcute_willupd_msg(argv[2], strlen(argv[2])) != EMCUTE_OK) {
        puts("error: unable to update the last will message");
        return 1;
    }

    puts("Successfully updated last will topic and message");
    return 0;
}

int get_next_value(float min, float max, char* data){
    //float value = (((float) rand()) % (max - min +1)) + min;
    float value = min + (rand() / (float) RAND_MAX) * (max - min);
    sprintf(data, "{Value: %f}", value);
    return 0;
}

int publish_sensor_data(emcute_topic_t topic_sensor, char* data_sensor, unsigned flags){
    if (emcute_pub(&topic_sensor, data_sensor, strlen(data_sensor), flags) != EMCUTE_OK) {
            printf("[Error]: can't publish data. Topic '%s [%i]'\n",
                    topic_sensor.name, (int)topic_sensor.id);
            return 1;
    }

    printf(" [Topic '%s [%i]']: published %i bytes\n", topic_sensor.name, topic_sensor.id, (int) strlen(data_sensor));

    //da cancellare
    printf("pub with topic: %s and value %s and flags 0x%02x\n\n", topic_sensor.name, data_sensor, (int)flags);

    sleep(3);

    return 0;
}

static int cmd_publish_environmental_station_data (int argc, char **argv) { 

    //Avoid errors
    (void) argc;
    (void) argv;
    
    //Settings to publish data
    emcute_topic_t topic_temperature_1;
    emcute_topic_t topic_temperature_2;

    emcute_topic_t topic_humidity_1;
    emcute_topic_t topic_humidity_2;

    emcute_topic_t topic_wind_direction_1;
    emcute_topic_t topic_wind_direction_2;

    emcute_topic_t topic_wind_intensity_1;
    emcute_topic_t topic_wind_intensity_2;

    emcute_topic_t topic_rain_height_1;
    emcute_topic_t topic_rain_height_2;

    unsigned flags = EMCUTE_QOS_0;

    //Initialize pseudo-random generator seed using current time (for rand())
    srand(time(0));
    
    //The user should use the command con to connect to the broker
    char data_temperature_1[128];
    char data_temperature_2[128];

    char data_humidity_1[128];
    char data_humidity_2[128];

    char data_wind_direction_1[128];
    char data_wind_direction_2[128];

    char data_wind_intensity_1[128];
    char data_wind_intensity_2[128];

    char data_rain_height_1[128];
    char data_rain_height_2[128];
    
     while (true) {

        //Get next sensor random value to publish
        get_next_value(min_temperature, max_temperature, data_temperature_1);
        get_next_value(min_temperature, max_temperature, data_temperature_2);

        get_next_value(min_humidity, max_humidity, data_humidity_1);
        get_next_value(min_humidity, max_humidity, data_humidity_2);

        get_next_value(min_wind_direction, max_wind_direction, data_wind_direction_1);
        get_next_value(min_wind_direction, max_wind_direction, data_wind_direction_2);

        get_next_value(min_wind_intensity, max_Wind_intensity, data_wind_intensity_1);
        get_next_value(min_wind_intensity, max_Wind_intensity, data_wind_intensity_2);

        get_next_value(min_rain_height, max_rain_height, data_rain_height_1);
        get_next_value(min_rain_height, max_rain_height, data_rain_height_2);
        
        printf ("[Debug]: data_temperature_1 =  %s\n", data_temperature_1);

        topic_temperature_1.name = "tmp1";
        topic_temperature_2.name = "tmp2";

        topic_humidity_1.name = "hum1";
        topic_humidity_2.name = "hum2";

        topic_wind_direction_1.name = "wdir1";
        topic_wind_direction_2.name = "wdir2";

        topic_wind_intensity_1.name = "wint1";
        topic_wind_intensity_2.name = "wint2";

        topic_rain_height_1.name = "rnhgt1";
        topic_rain_height_2.name = "rnhgt2";

        //Get topic ID        
        if (emcute_reg(&topic_temperature_1) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_temperature_2) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_humidity_1) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_humidity_2) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_wind_direction_1) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_wind_direction_2) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_wind_intensity_1) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_wind_intensity_2) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_rain_height_1) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }
        if (emcute_reg(&topic_rain_height_2) != EMCUTE_OK) {
            puts("error: unable to obtain topic ID");
            return 1;
        }

        //Publish data for temperature topic
        publish_sensor_data(topic_temperature_1, data_temperature_1, flags);
        publish_sensor_data(topic_temperature_2, data_temperature_2, flags);

        //Publish data for humidity topic
        publish_sensor_data(topic_humidity_1, data_humidity_1, flags);
        publish_sensor_data(topic_humidity_2, data_humidity_2, flags);

        //Publish data for wind direction topic
        publish_sensor_data(topic_wind_direction_1, data_wind_direction_1, flags);
        publish_sensor_data(topic_wind_direction_2, data_wind_direction_2, flags);

        //Publish data for wind_intensity topic
        publish_sensor_data(topic_wind_intensity_1, data_wind_intensity_1, flags);
        publish_sensor_data(topic_wind_intensity_2, data_wind_intensity_2, flags);

        //Publish data for rain heigth topic
        publish_sensor_data(topic_rain_height_1, data_rain_height_1, flags);
        publish_sensor_data(topic_rain_height_2, data_rain_height_2, flags);
    }
    return 0;
}

static const shell_command_t shell_commands[] = {
    { "con", "connect to MQTT broker", cmd_con },
    { "discon", "disconnect from the current broker", cmd_discon },
    { "pub", "publish something", cmd_pub },
    { "pub_ES_data", "publish sensors' data for both environmental stations", cmd_publish_environmental_station_data },
    { "sub", "subscribe topic", cmd_sub },
    { "unsub", "unsubscribe from topic", cmd_unsub },
    { "will", "register a last will", cmd_will },
    { NULL, NULL, NULL }
};

int main(void)
{
    puts("Environmental stations simulator.\n");
    puts("Type 'help' to get started. Have a look at the README.md for more"
         "information.");

    /* the main thread needs a msg queue to be able to run `ping6`*/
    msg_init_queue(queue, (sizeof(queue) / sizeof(msg_t)));

    /* initialize our subscription buffers */
    memset(subscriptions, 0, (NUMOFSUBS * sizeof(emcute_sub_t)));

    /* start the emcute thread */
    thread_create(stack, sizeof(stack), EMCUTE_PRIO, 0,
                  emcute_thread, NULL, "emcute");

    /* start shell */
    char line_buf[SHELL_DEFAULT_BUFSIZE];
    shell_run(shell_commands, line_buf, SHELL_DEFAULT_BUFSIZE);

    /* should be never reached */
    return 0;
}
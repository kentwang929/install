import install_utils as utils
import sys
import re

COLLECTD_HOME="/etc/collectd"
COLLECTD_CONF_DIR=COLLECTD_HOME+"/managed_config"

# http response header
NOT_AUTH = 2
NOT_FOUND = 1
HTTP_OK = 0
INVALID_URL = -1

def check_collectd_exists():
    print "Checking if collectd exists"
    if not utils.command_exists("collectd"):
        sys.stderr.write("Collectd is not installed.\n"
            "Please rerun the installer with --collectd option.\n")
        sys.exit()

def check_collectd_path():
    print "Checking if collectd is installed in our specified directory"
    res = utils.check_path_exists(COLLECTD_HOME)
    if not res:
        sys.stderr.write("Collectd was not found at our "
            "default installation folder. "
            "If you need help with configuration, please "
            "contact support@wavefront.com\n")
        sys.exit()

def check_collectd_conf_dir():
    """
    Check if managed_config directory exists, if not, 
    create one.
    """
    res = utils.check_path_exists(COLLECTD_CONF_DIR)
    if not res:
        print "Creating collectd managed config dir"
        utils.call_command("mkdir "+COLLECTD_CONF_DIR)

def check_install_state(plugin):
    print ("Cannot check install state yet.")
    return False

def write_tcpconns_conf_plugin(open_ports):
    """
    TODO:
    -need to check if tcpconn plugin's dependencies are installed
    -include RemotePort for outbounds connections
        i.e. the servers we are connecting to
    """
    try:
        out = open("10-tcpconns.conf", "w")
    except:
        sys.stderr.write("Unable to write tcpcons.conf file\n")
        sys.exit()
   
    out.write('LoadPlugin tcpconns')
    out.write('<Plugin "tcpconns">\n')
    out.write('  ListeningPorts false\n')
    for port in open_ports:
        out.write('  LocalPort "%d"\n' % port)
    # no remote port yet
    out.write('</Plugin>\n')
    out.close()

def include_apache_es_conf(dir):
    """
    Assume extendedstatus.conf is unique to wavefront and writing over it.
    """
    out = utils.write_file(dir+"/extendedstatus.conf")
    if out is None:
        utils.exit_with_message("Unexpected error!")

    out.write(''
        '# ExtendedStatus controls whether Apache will generate "full" status\n'
        '# information (ExtendedStatus On) or just basic information (ExtendedStatus\n'
        '# Off) when the "server-status" handler is called. The default is Off.\n'
        'ExtendedStatus on')
    out.close()


# Apache Installation
def apache_title():
  sys.stdout.write(""
  " _____ __________  _____  _________   ___ ______________\n"
  "   /  _  \\______   \/  _  \ \_   ___ \ /   |   \_   _____/\n"
  "  /  /_\  \|     ___/  /_\  \/    \  \//    ~    \    __)_ \n"
  " /    |    \    |  /    |    \     \___\    Y    /        \ \n"
  " \____|__  /____|  \____|__  /\______  /\___|_  /_______  /\n"
  "         \/                \/        \/       \/        \/ \n")

def install_apache_plugin():
    apache_title()
    install = check_install_state("Apache")
    print ""
    if not install:
        print "This script has detected that you have apache installed and running."
        res = utils.ask("Would you like collectd to collect data from apache")
    else:
        print "You have previously installed this plugin."
        res = utils.ask("Would you like to reinstall this plugin", no)

    if not res:
        return

    utils.print_step("Begin collectd Apache plugin installer")

    """
    - check dependency
    - change system file
    - check mod status
    - TODO: pull template
    - prompt for user information
    """
    if not utils.command_exists("curl"):
        utils.exit_with_failure("Curl is needed for this plugin.")

    # ubuntu check
    # Assuming latest apache2 is installed and the installation
    # directory is in the default place
    utils.print_step("Checking if mod_status is enabled")
    cmd_res = utils.get_command_output("ls /etc/apache2/mods-enabled")
    if "status.conf" not in cmd_res or "status.load" not in cmd_res: 
        utils.print_step("Enabling apache2 mod_status module.")
        ret = utils.call_command("sudo a2enmod status")
        if ret != 0:
            utils.exit_with_message("a2enmod command was not found")

    utils.print_success()
    print ""
    sys.stdout.write("In order to enable the apache plugin with collectd, the "
                     "ExtendedStatus setting must be turned on.\n")
    res = utils.ask("Has this setting been set?", "no")

    """
    missing the flow where user wants to turn on the setting themselves. 
    """
    if not res:
        res = utils.ask("Would you like us to include the config file for such setting?")
        if res:
            # include the config file in /apache2/conf-enabled
            conf_dir = "/etc/apache2/conf-enabled"
            utils.print_step("Checking if "+conf_dir+" exists.")
            if utils.check_path_exists(conf_dir):
                # pull config file here
                utils.print_success()
                include_apache_es_conf(conf_dir)
                sys.stdout.write("\nextendedstatus.conf is now included in the "+
                                 conf_dir+" dir.\n")
                print ""
                ret = utils.call_command("service apache2 restart")
                if ret != 0:
                    utils.exit_with_message("Failed to restart apache service")
            else:
                exit_with_message(conf_dir + " dir does not exist, "+
                                  "please consult support@wavefront.com"+
                                  "for any additional help.")
        else:
            utils.print_warn("Collectd plugin will not work if the "
                             "ExtendedStatus is not turned on.")
            utils.exit_with_message("Consult support@wavefront.com for any "
                "additional help.")

    # Begin writing apache plugin
    utils.print_step("Begin writing apache plugin for collectd")
    plugin_file = "wavefront_temp_apache.conf"
    out = utils.write_file(plugin_file)
    error = False
    if out is None:
        utils.exit_with_message("")

    try:
        res = write_apache_plugin(out)
    except:
        sys.stderr.write("Unexpected flow\n")
        error = True
    finally:
        out.close()
        if error:
            sys.stderr.write("Closing and removing temp file")
            utils.call_command("rm "+plugin_file)
            print ""
            sys.exit()

    # if there was at least one instance being monitor
    if res:
        utils.print_step("Copying the plugin file to the correct place")
        cp_cmd = "cp "+plugin_file+" "+ \
                  COLLECTD_CONF_DIR+ \
                 "/wavefront_apache.conf"
        ret = utils.call_command(cp_cmd)

        if ret == 0:
            utils.print_success()
            print "Apache_plugin has been written successfully."
            print ""
            utils.call_command("service collectd restart")
            print ""
            sys.stdout.write("To check if this plugin has been successfully, "
                  "please check if apache. is included in your "
                  "browse metric page.\n")
        else:
            exit_with_message("Failed to copy the plugin file.\n")
    else:
        sys.stdout.write("You did not provide any instance to monitor.\n")

    utils.call_command("rm "+plugin_file)

def check_http_response(http_res):
    http_status_re = re.match("HTTP/1.1 (\d* [\w ]*)\s", http_res) 
    if http_status_re is None:
        utils.print_warn("Invalid http response header!")
        sys.exit()

    http_code = http_status_re.group(1)

    if( "401 Unauthorized" in http_code ):
        return NOT_AUTH
    elif( "404 Not Found" in http_code ):
        return NOT_FOUND
    elif( "200 OK" in http_code ):
        return HTTP_OK
    else:
        return INVALID_URL
        
def check_apache_server_status(payload):
    atitle_re = re.search(r'(<head>[\w\W\s]*<title>Apache '+
        'Status</title>[\w\W\s]*</head>)([\w\W\s]*)', payload)

    if atitle_re is not None:
        res = atitle_re.group(2)
        ah1_re = re.search(r'<h1>(Apache Server Status for )([\w\W]*?)</h1>',
                  res)
        if ah1_re is not None:
            res = ah1_re.group(1) + ah1_re.group(2)
            return res

    return None

def write_apache_plugin(out):
    # COLLECTD_CONF_DIR+"/10-apache.conf")
    out.write('LoadPlugin "apache"\n')
    out.write('<Plugin "apache">\n')

    count = 0
    server_list = []

    print ""
    sys.stdout.write("To monitor a apache server, "
        "you must add/have something similar to the configuration file:\n"
        "<Location /server-status>\n"
        "  SetHandler server-status\n"
        "</Location>\n"
        "to enable the status support.\n")
 
    while(utils.ask("Would you like to add a new instance to monitor?")):
        url = utils.get_input("Please enter the url that contains your "+
                              "server-status:")
        print ""
        utils.print_step("Checking http response for %s" % url)
        res = utils.get_command_output('curl -s -i '+url)

        if res is None:
            ret = INVALID_URL
        else:
            ret = check_http_response(res)

        if ret == NOT_AUTH:
            # skip for this case for now, ask for user/pass
            sys.stderr.write("Authorization server status is required, please "
                            "try again.\n")
        elif ret == NOT_FOUND or ret == INVALID_URL:
            utils.print_failure()
            sys.stderr.write("Invalid url was provided, please try "
                            "again.\n")
        elif ret == HTTP_OK:
            utils.print_success()
            if url in server_list:
                utils.print_warn("You have already added this url") 
            else:
                res = check_apache_server_status(res)
                if res is None:
                    utils.print_warn("The url you have provided "+
                        "does not seem to be the correct server_status "+
                        "page.  Incorrect server-status will not be recorded "+
                        "by collectd.")
                    utils.ask("Would you like to record this url anyway?", "no")
                else:
                    print res
                    res = utils.ask("Is this the correct status to monitor?")
                    print ""
                    if res:
                        count = count + 1
                        server_list.append(url)
                        instance = "apache%d" % count 
                        url_auto = url+"?auto"
                        out.write('  <Instance "'+instance+'">\n')
                        out.write('    URL "'+url_auto+'"\n')
                        out.write('  </Instance>\n')

    out.write('</Plugin>\n')
    return count

if __name__ == "__main__":
    print "Testing conf_collected_plugin"
    print COLLECTD_HOME
    print COLLECTD_CONF_DIR
    print "Curls command: ", utils.command_exists("curl")
    
    url = raw_input("Enter a url to check:\n")
    check_apache_server_status(url)
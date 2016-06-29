import install_utils as utils
import sys

COLLECTD_HOME="/etc/collectd"
COLLECTD_CONF_DIR=COLLECTD_HOME+"/managed_config"

# http response header
NOT_AUTH = 2
NOT_FOUND = 1
HTTP_OK = 0

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
    print ("Cannot check %s yet." % plugin)
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

def install_apache_plugin():
    print "---Apache---"
    install = check_install_state("Apache")
    if not install:
        print "This script has detected that you have apache installed and running."
        res = utils.ask("Would you like collectd to collect data from apache")
    else:
        print "You have previously installed this plugin."
        res = utils.ask("Would you like to reinstall this plugin", no)

    if not res:
        return

    print "---Begin collectd Apache plugin installer---"

    """
    - check dependency
    - change system file
    - check mod status
    - TODO: pull template
    - prompt for user information
    """
    if not utils.command_exists("curl"):
        utils.exit_with_message("Curl is needed for this plugin")

    # ubuntu check
    # Assuming latest apache2 is installed and the installation
    # directory is in the default place
    cmd_res = utils.get_command_output("ls /etc/apache2/mods-enabled")
    if "status.conf" not in cmd_res or "status.load" not in cmd_res: 
        print "Enabling apache2 mod_status module."
        ret = utils.call_command("sudo a2enmod status")
        if ret != 0:
            utils.exit_with_message("a2enmod command was not found")

    sys.stdout.write("In order to enable the apache plugin with collectd, the "
                     "ExtendedStatus setting must be turned on.")
    res = utils.ask("Has this setting been set?", "no")

    """
    missing the flow where user wants to turn on the setting themselves. 
    """
    if not res:
        res = utils.ask("Would you like us to include the config file for such setting?")
        if res:
            # include the config file in /apache2/conf-enabled
            conf_dir = "/etc/apache2/conf-enabled"
            if utils.check_path_exists(conf_dir):
                # pull config file here
                include_apache_es_conf(conf_dir)
                sys.stdout.write("extendedstatus.conf is now included in the "
                             "apache2/conf-enabled dir.")
            else:
                exit_with_message("conf-enabled dir does not exist, "+
                                  "please consult support@wavefront.com"+
                                  "for any additional help.")
        else:
            utils.exit_with_message("Consult support@wavefront.com for any "
                "additional help.")

    out = utils.write_file("wavefront_temp_apache")
    error = False
    if out is None:
        utils.exit_with_message("")

    try:
        res = write_apache_plugin()
    except:
        sys.stderr.write("Unexpected flow\n")
        error = True
    finally:
        if error:
            sys.stderr.write("Closing and rming temp file")
            out.close
            utils.call_command("rm wavefront_temp_apache")

    # apache_plugn_name has been written to $location
    if res:
        print "Apache_plugin has been written successfully."
        utils.call_command("cp wavefront_temp_apache "+
                            COLLECTD_CONF_DIR)
        utils.call_command("rm wavefront_temp_apache")
        print "Restarting collectd service"
        utils.call_command("sudo service collectd restart")
        sys.stdout.write("To check if this plugin has been successfully, "
              "please check if apache. is included in your "
              "browse metric page.")

    # restart after the configuration 
    # pull the appropriate template

def check_apache_server_status(url):
    res = utils.get_http_status(url)

    if( "401 Unauthorized" in res ):
        return NOT_AUTH
    elif( "404 Not Found" in res ):
        return NOT_FOUND
    elif( "200 OK" in res ):
        return HTTP_OK
        
def write_apache_plugin(out):
    # COLLECTD_CONF_DIR+"/10-apache.conf")
    out.write('LoadPlugin "apache"')
    out.write('<Plugin "apache">\n')

    count = 0
    server_list = []

    sys.stdout.write("To monitor a apache server, "
        "you must have/add something similar to the configuration file:\n"
        "<Location /server-status>\n"
        "  SetHandler server-status\n"
        "</Location>\n"
        "to enable the status support.")
 
    while(ask("Would you like to add a new instance to monitor?")):
        url = utils.get_input("Please enter the url that contains your "+
                              "server-status:")
        ret = check_apache_server_status(url)

        if ret == NOT_AUTH:
            # skip for this case for now, ask for user/pass
            sys.stderr.write("Authorization server status is required, please "
                            "try again.")
        elif ret == NOT_FOUND:
            sys.stderr.write("Invalid url was provided, please try "
                            "again.")
        elif ret == HTTP_OK:
            count = count + 1
            instance = "apache%d" % count 
            url_auto = url+"?auto"
            out.write('  <Instance "'+instance+'">\n')
            out.write('    URL '+url_auto+'\n')
            out.write('  </Instance>\n')
            sys.stdout.write("Url was fetched successfully, "+instance+
                " will monitor "+url)

    out.write('</Plugin>\n')
    return True

if __name__ == "__main__":
    print "Testing conf_collected_plugin"
    print COLLECTD_HOME
    print COLLECTD_CONF_DIR
    print utils.command_exists("curl")
    #    check_collectd_path()

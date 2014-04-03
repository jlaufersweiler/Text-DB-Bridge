#!/usr/bin/env python
'''EZ DB Tool:
    * Read operating parameters from a config file.
    * Open an ODBC connection and create a cursor object.
    * Execute arbitrary SQL statements from text files.
    * Write output from SQL operation to a CSV file.'''

#import csv, pyodbc, ConfigParser,subprocess
import csv, ConfigParser,subprocess
from optparse import OptionParser
from getpass import getpass
from textwrap import wrap
from os import path
from os import remove
from sys import argv,stdin,stdout,platform

########### Toolbox ###########
def delfile(path):
    '''Deletes a file from the filesystem.'''
    try:
        remove(path)
    except:
        print "Problem deleting file %s." % path
def yesno(prompt='CHOICE(y/n):'):
    '''Request a yes or no answer from the user, return True or False.'''
    while True:
        answer=raw_input(prompt)
        if answer.lower() not in ('y','n','yes','no'): #reject invalid response
            print 'Invalid entry.'
            continue
        else:
            break
    if answer.lower()[0]=='y': #test based on first character
        return True
    else:
        return False

def confirm(choice,promptstring=None):
    '''Confirm choice with yes or no input, returning True or False.
    If no prompt string passed, default value is used.
    Prompt string may contain format string precent-sub for choice or \n for new line.'''
    default="You chose: %s \nIs this correct? (y/n):" % choice
    if promptstring==None:
        prompt=default
    else:
        prompt=promptstring % choice
    return yesno(prompt)

def trim80(string,width=80):
    '''Returns a up to the first 80 characters of a string.
    Width may optionally be overridden'''
    try: #slice string
        return string[0:width]
    except: #if passed other than a string, make a string first
        return str(string)[0:width]
		
class DataSourceLookup(ConfigParser.SafeConfigParser):
    '''Config parser for reading odbc.ini files from OS
    Accesses info about drivers and DSNs present (read only).'''
    #def __init__(self,mode='system',syspath='/Library/ODBC/odbc.ini',userpath='~/Library/ODBC/odbc.ini'):
    def __init__(self,mode='system',syspath='fakesysodbc.ini',userpath='fakeuserodbc.ini'):
        '''Creates parser, and sets paths for system or user odbc.ini file.
        Default odbc.ini paths for MacOS + iODBC provided, but may be overridden for a given instance.'''
        if mode.lower() not in ('system','sys','user','usr'): #check for valid mode
            print "Invalid mode: '%s'" % mode
            return None
        else: #set mode to system or user data sources.  Default is system
            self.mode=mode.lower()
        if self.mode[0:2]=='sys': #point at system file...
            self.file=syspath
        else: #...or user file, according to mode
            self.file=userpath
        ConfigParser.SafeConfigParser.__init__(self) #build parser
        with open(self.file,"r") as odbcfile: #load data from file, then close
            self.read(odbcfile)
    def write(self,target=None):
        '''Parent class overridden on object to force readonly operation.'''
        print "Changes to odbc.ini not allowed with this tool."
    def set(self,section=None,option=None,value=None):
        '''Parent class overridden on object to force readonly operation.'''
        print "Changes to to odbc.ini not allowed with this tool."
    def remove_section(self,section=None):
        '''Parent class overridden on object to force readonly operation.'''
        print "Changes to to odbc.ini not allowed with this tool."
    def remove_option(self,section=None,option=None):
        '''Parent class overridden on object to force readonly operation.'''
        print "Changes to to odbc.ini not allowed with this tool."


class ConfigHandler(ConfigParser.SafeConfigParser):
    '''Generates and interperets configuration files for download operations.
    Called with mode argument for app settings or query operation'''
    def __init__(self,mode,file=None): #default config file name for mode used if file not passed
        '''Looks for config or queries file, creates if absent, checks for data.'''
        self.modes={'settings':'Download Profile List','queries':'Query List'}
        self.missing=[]
        self.orphan=[]
        self.empty=[]
        if mode.lower() in self.modes.keys(): #sets config mode for object
            self.mode=mode.lower()
        else: #reject invalid mode argument and return None
            print "Invalid Configuration Mode: %s" % mode
            return None
        if file==None: #use default file name in current directory
            configfile=''.join([self.mode,'.config'])
        else: #or use custom name or path passed to init
            configfile=file
        if not path.exists(configfile): #creates file if absent and instantiates handler and add empty index section
            self.newconfig=True
            try: #create new config file
                with open(configfile,'w') :
                    print "Creating file: %s" % configfile
            except:#return None if unable to create file
                print "Unable to create file: %s" % configfile
                return None
            self.configfile=configfile
            ConfigParser.SafeConfigParser.__init__(self)
            self.optionxform=str
            self.add_section(self.modes[self.mode])
            self.consistant=True
        else: #instantiates handler and looks for config data in file
            self.configfile=configfile
            ConfigParser.SafeConfigParser.__init__(self)
            try: #load existing config data
                self.read(self.configfile)
            except: #return None if unable to read data
                print "Unable to read data from file: %s" % configfile
                return None
            if len(self.sections())==0: # Test for no config sections
                self.newconfig=True
                self.consistant=True
                self.add_section(self.modes[self.mode])
                print "%s data not present in %s\nConfiguration required." % (self.mode.title(),self.configfile)
            elif self.has_section(self.modes[self.mode])==False: # Test for no index section
                self.newconfig=True
                self.consistant=False
                self.add_section(self.modes[self.mode])
                print "No %s section in %s\nConfiguration required." % (self.options(self.modes[self.mode]),self.configfile)
            elif len(self.options(self.modes[self.mode]))==0: # Test for empty index section
                self.newconfig=True
                self.consistant=False
                
            else: #index section is present and not empty...
                self.newconfig=False
                if set(self.sections()).difference(set(self.options(self.modes[self.mode])))==set([self.modes[self.mode]]):#check index:section consistancy
                    self.consistant=True #if and only if the index section exactly lists all other sections
                else: #if index:section mismatch, identify and warn.
                    for item in set(self.options(self.modes[self.mode])).difference(set(self.sections())): #list missing sections
                        self.missing.append(item)
                        print "'%s' is listed in %s but has no matching configuration section." % (item,self.modes[self.mode])
                    for item in set(self.sections()).difference(set(self.options(self.modes[self.mode]))).difference(set([self.modes[self.mode]])): #list sections not in index (excluding index itself)
                        self.orphan.append(item)
                        print "Configuration section '%s' is present, but not listed in %s section." % (item,self.modes[self.mode])
                    print 'Check Configuration'
                    self.consistant=False
                for item in set(self.options(self.modes[self.mode])).intersection(set(self.sections())): #check present indexed sections for zero length.
                    if len(self.options(item))>0:
                        pass
                    else:
                        self.empty.append(item)
                        print "'%s' configuration section present but is empty." % item
        if len(self.empty)>0: # Print empty count.
            print "%s empty in %s\nConfiguration required." % (self.options(self.modes[self.mode]),self.configfile)
            
        if self.newconfig==False: #init done
            pass 
        else: #Write index section to file if new.
            with open(self.configfile,'r+') as file:
                 self.write(file)
    def muddle(self,string,delim='l',salt=42):
        '''Obscures sensative data in config file.'''
        pieces=[]
        try:
            for char in string:
                pieces.append(str(ord(char)+salt))
        except TypeError:
            string=str(string)
            for char in string:
                pieces.append(str(ord(char)+salt))
        return delim.join(pieces)
        ### This is a weak substitution cipher to counfound casual snoopers, but still be hand editable in the config file during testing.
        ### Don't use it oustide of that context.
		### This will be replaced with a proper hash operation when released.

    def unmuddle(self,string,delim='l',salt=42):
        '''Decodes value encoded by muddle.'''
        try:
            pieces=string.split(delim)
        except TypeError:
            string=str(string)
            pieces=string.split(delim)
        frags=[]
        for num in pieces:
            frags.append(chr(int(num)-salt))
        return ''.join(frags)

    def writeconfig(self):
        '''Saves configuration data to file.'''
        try:
            with open(self.configfile,'w+') as f:
                self.write(f)
            print "Writing %s data to file: %s" % (self.mode,self.configfile)
            return True
        except:
            print "PROBLEM WRITING %s DATA TO FILE: %s" % (self.mode,self.configfile)
            return False

    def listconfigs(self):
        '''Return list of tuples containing (name,description) pairs of queries or download profiles, according to object mode.'''
        return self.items(self.modes[self.mode])
    def addconfig(self,name,description):
        '''Add new section and add name and description to index section'''
        self.add_section(name.lower())
        self.set(self.modes[self.mode],name.lower(),description)
    def delconfig(self,name):
        '''Remove section and its index section entry.'''
        if confirm(name,"About to delete '%s'\nARE YOU SURE(y/n):")==True: #confirm deletion
            if self.consistant==True: #normal deletion
                self.remove_option(self.modes[self.mode],name)
                self.remove_section(name)
                print "Config section '%s' deleted and removed from %s"
            else: #warn of inconsistancy, but still delete.
                if self.remove_option(self.modes[self.mode],name)==True:
                    print "%s removed from %s" % (name,self.modes[self.mode],)
                else:
                    print "Config section '%s' is not listed in %s./nAttempting to delete section..." % (name,self.modes[self.mode])
                if self.remove_section(name)==True:
                    print "Config section '%s' deleted." % name
                else:
                    print "Config section '%s' not present." % name
        else: #deletion cancelled
            print "Deletion cancelled."
    def modconfig(self,section,opts={}):
        '''Set or change query or app settings, according to object mode.
        Pass {option_name:None} to remove an option. All items stored as strings.
        If section is index section, may only change descritption values.'''
        if section!=self.modes[self.mode]: #Modify options:values in aconfig section (not index section)
            if self.has_section(section)==True: #test if section exists
                for opt in opts.items(): # do changes
                    if opt[1]!=None: #sets option, creating if new, overwriting if already present.
                        try: #set option to value
                            self.set(section,opt[0],opt[1])
                        except TypeError: #converts value to string if necessary
                            self.set(section,opt[0],str(opt[1]))
                        print '''Option "%s" in %s set to "%s"''' % (opt[0],section,opt[1])
                    else: #delete option from section if None passed for new value
                        if self.remove_option(section,opt[0])==True: # delete option if present
                            print '''Option "%s" deleted from %s''' % (opt[0],section)
                        else: #if option wasn't there to begin with, do nothing
                            print '''Option "%s" was not present in %s''' % (opt[0],section)
                            print '\tNo action taken.'
            else: #Do nothing if section invalid
                print '''Section "%s" not found.''' % section
        else: #Change description of config in index section
            for opt in opts.items():
                if opt[0] not in self.options(section): #test for index entry
                    print '''"%s" not listed in %s''' % (opt[0],section)
                    print '%s not changed.' % section
                    continue
                elif opt[1]==('' or None): # prevent blank description
                    print "Description may not be blank.\n %s entry for %s unchanged" % (section,opt[0])
                    continue
                else: #update description in index
                    try: #set descripion to new value
                        self.set(section,opt[0],opt[1])
                    except TypeError: #converts value to string if necessary
                        self.set(section,opt[0],str(opt[1]))
    def getconfig(self,section,opts='all'):
        '''Return dictionary of option:value pairs from query or download profile, according to object mode.
        Returns all values by default, but opts may take a list one or more specific values.
        All values returned as strings, unless for a missing option, which returns option:None.'''
        data={} #container for retrieved option:value mappings
        if opts=='all': #return entire section
            for opt in self.items(section.lower()):
                data.update({opt[0]:opt[1]})
        else: #return specific option:value pairs from passed list of options
            for opt in opts:
                if self.has_option(section.lower(),opt)==True: #get value if option set
                    data.update({opt:self.get(section.lower(),opt)})
                else: # get None if value absent
                   data.update({opt:None})
        return data

    def repair(self):
        '''Reconcile inconsistencies between index and config sections.'''
        while len(self.missing)>0: #reconcile index entries with no config section
            name=self.missing.pop() #take entry from end of missing list
            print '''"%s" is listed in %s, but has no corresponding congfiguration section.''' % (name,self.modes[self.mode])
            while True: #choose add or delete
                choice=raw_input("Enter 'd' to delete from index, or 'a' to add new empty config section.\nCHOICE(d/a):")
                if choice.lower() not in ('a','d','add','delete'): #reject invalid response
                    print "Invalid Entry."
                    continue
                else: #confirm choice
                    if confirm(choice)==True:
                        break
                    else:
                        continue
            if choice.lower()[0]=='a': #add empty config section
                self.add_section(name)
                self.empty.append(name)
                print "Configuration section '%s' added." % name
            else: #remove missing config section from index
                self.remove_option(self.modes[self.mode],name)
                print "Entry '%s' removed from %s" % (name,self.modes[self.mode])
        while len(self.orphans)>0: #reconcile config sections not listed in index
            name=self.orphan.pop() #take entry from end of orphan list
            print '''Congfiguration section "%s" is present but not listed in %s.''' % (name,self.modes[self.mode])
            while True: #choose add or delete
                choice=raw_input("Enter 'd' to delete section, or 'a' to add new entry in %s.\nCHOICE(d/a):" % self.modes[self.mode])
                if choice.lower() not in ('a','d','add','delete'): #reject invalid response
                    print "Invalid Entry."
                    continue
                else: #confirm choice
                    if confirm(choice)==True:
                        break
                    else:
                        continue
            if choice.lower()[0]=='a': #get description and add to index
                while True: # enter description for index entry
                    desc=raw_input("Enter description for '%s'\nDESC:" % name)
                    if len(desc)==0: #reject empty string
                        print "Description may not be blank."
                        continue
                    else: # Proofread input
                        if confirm(desc)==True:
                            break
                        else:
                            continue
                self.set(self.modes[self.mode],name,desc) #add entry to index
                print '''"%s" added to %s.''' % (name,self.modes[self.mode])
            else: #remove orphan config section
                self.remove_section(name)
                print "Configuration section '%s' removed." % name
        print "Repair complete."
        self.consistant=True









def querysetup(file='default'):
    '''Add or modify query configuration.'''
    print '\n\n**********QUERY FILE SETUP**********\n\n'
    def handler():
        '''Initializes config handler for setup'''
        if file=='default': #instantiate config handler with default file name
            return ConfigHandler('queries')
        else: #instantiate config handler with custom file name
            return ConfigHandler('queries',file)
    def editquery(name):
        '''Edit query in console text editor.'''
        tname='.'.join([name.lower(),'edit']) #creates name for tempfile/edit buffer
        try: #get list of lines from existing SQL (edit old query)
            edlines=cf.get(name.lower(),'sql').splitlines(keep=True)
        except: #no SQL found. create empty line list  (new or empty query)
            edlines=[]
        instructions='''Lines beginning with '#' or ';' are ignored and will not be passed to the database. Question marks may be used for parameters passed by the download profile.''' #Help lines to be appended to the edit-tempfile as comments.
        lines=wrap(instructions,width=78) # append instructions to editbuffer
        while len(lines)>0:
            edlines.append(''''''.join(['\n# ',lines.pop(0)])) #appends instructions from last to first, maintaining sequence.
        with open(tname,'w+') as f: #create temp file,appends instructions/old SQL, then closes file.
            f.writelines(edlines) #writes instructions, then existing SQL (if any) to temp file
        if platform!='win32': #set external editor to nano if *nix...
            editor='nano'
            save="Control+O ('Write Out')"
            quit="Control+X ('Exit')"
        else: # ...or 'edit' if windows
            editor='edit'
            save="Alt+F then S ('File->Save')"
            quit="Alt+F then X ('File->Exit')"
        print "**You are about to enter an interactive editing console.**"
        for l in wrap("When you have finished entering/editing your SQL statements, use %s to save your query. Then, use %s to leave the editor to return to this environment." % (save,quit),width=80):
            print l
        go=raw_input("Press Enter or Return to begin edit session.") #prompt just for pause before calling shell editor. input not evaluated
        go=None #discard any junk that may have been entered at prompt, just in case.
        try: #open tempfile in external editor, wait for editor process to teminate successfully
            subprocess.check_call([editor,tname])
        except CalledProcessError: #If external text editor process fails, delete temp file and return False
            delfile(tname)
            return False
        with open(tname,'r') as temp:#read data back from tempfile then close it
            qtxt=temp.read()
        delfile(tname) #delete tempfile
        if len(qtxt)>0: #add SQL to config section, if present
            cf.modconfig(name.lower(),{'sql':qtxt})
            return True
        else: # otherwise do nothing, return False
            return False



    def addquery():
        '''Interactively name and describe new query sections.
        SQL may be input at creation or added later.'''
        if yesno("Add query section?(y/n):")==False: #If choice is n, cancel.
            print "Addition cancelled."
        else: #If choice is y, add one or more queries; optionally entering SQL as well.
            while True: #add/edit loop
                while True: #input name
                    qname=raw_input("Enter name for query.\nNAME:")
                    if len(qname)==0: #reject blank
                        print "Query name may not be blank."
                        continue
                    else:
                        break
                while True: #input description
                    qdesc=raw_input("Enter description string for query, '%s'.\nBe sure to list any parameter variables, if required.\nDESC:" % qname)
                    if len(qdesc)==0: #reject blank
                        print "Query description may not be blank."
                        continue
                    else:
                        break
                cf.addconfig(qname,qdesc) #adds new query to configuration
                print "Query section '%s' added.\n" % qname
                if yesno("Enter query SQL now?(y/n):")==True: #call editor
                    while True: #editor loop
                        if editquery(qname)==True: #SQL entry successful, exit edit sub-loop
                            print ("Query configured.")
                            break
                        else: #SQL entry failed. try again?
                            if yesno("Problem entering SQL.\nTry again?(y/n):")==True: #retry entry
                                continue
                            else: #log empty query section and exit edit sub-loop
                                cf.empty.append(qname) #adds to list of empty configs
                                break
                else: #log empty query section
                    cf.empty.append(qname) #adds to list of empty configs
                if yesno("Add another query section?(y/n):")==True: #loop again
                    continue
                else: #exit add/edit loop
                    break
    def save():
        '''Write config data to file.'''
        while True:
            if cf.writeconfig()==True:
                return True
            else:
                if yesno('Make sure the file is not open in another program.\nTry again?(y/n):')==True:
                    continue
                else:
                    return False
    def menu():
        '''Presents options to view, modify, and save configuration data.
        Repeats until menuloop is set to False by selected menu operation.'''
        def dochoice(choice):
            '''Carry out operation selected by user.'''
            def qpick():
                '''Choose query from list of those in index section, return query name.'''
                print '*****AVAILABLE QUERIES*****'
                for q in cf.listconfigs(): #show numbered list of queries and up to
                    if q[0] in cf.empty:
                        print trim80('\t%s  %s\t%s (SQL EMPTY)' % (cf.listconfigs().index(q)+1,q[0],q[1]))
                    else:
                        print trim80('\t%s  %s\t%s' % (cf.listconfigs().index(q)+1,q[0],q[1]))
                while True: #enter and confirm selection
                    input=raw_input('Enter the number for your selection.\nCHOICE?:')
                    try: #entry must be integer
                        choice=int(input)
                    except:
                        print "Choice must be a number"
                        continue
                    if (choice-1) not in range(0,len(cf.listconfigs())):
                        print 'Invalid selection: %s' % input
                        continue
                    else:
                        if confirm(cf.listconfigs()[choice-1][0])==True:
                            return cf.listconfigs()[choice-1][0]
                        else:
                            continue

        #### menu operations ####
            if choice=='0': #Repair configuration
                cf.repair
                return True
            elif choice=='1': # List queries note if SQL is empty
                print '*****AVAILABLE QUERIES*****'
                for q in cf.listconfigs():
                    if q in cf.empty:
                        print trim80('\t%s (SQL EMPTY) %s' % (q[0],q[1]))
                    else:
                        print trim80('\t%s  %s' % (q[0],q[1]))
                return True
            elif choice=='2': # Query detail view
                qname=qpick()
                print "QUERY: %s" % qname
                print "DESCRIPTION: %s" % cf.get(cf.modes[cf.mode],qname)
                try:
                    print "SQL: %s" % cf.get(qname,'sql')
                except:
                    print "SQL: NOT SET"
                return True
            elif choice=='3': #Edit query SQL
                qname=qpick() #choose query section to edit
                while True: #editor loop
                        if editquery(qname)==True: #SQL entry successful, exit edit sub-loop
                            print ("Query '%s' configured.") % qname
                            break
                        else: #SQL entry failed. try again?
                            if yesno("Problem entering SQL.\nTry again?(y/n):")==True: #retry entry
                                continue
                            else: #exit edit sub-loop
                                break
                #update empty config list
                if qname in cf.empty: #if in empty list
                    if cf.has_option(qname,'sql') and len(cf.get(qname,'sql'))>0: #remove from empty list if SQL present
                        cf.empty.remove(qname)
                else: #if not in empty list
                    if not (cf.has_option(qname,'sql') or len(cf.get(qname,'sql'))>0): #add to list if no SQL configured
                        cf.empty.append(qname)
                return True
            elif choice=='4': #Edit query description
                qname=qpick()
                while True: #Display old, then enter new
                    print "QUERY: %s" % qname
                    print "CURRENT DESCRIPTION:\n%s\n" % cf.get(cf.modes[cf.mode],qname)
                    new=raw_input("ENTER NEW DESCRIPTION:")
                    if new!='': #if entry not empty string,confirm, cancel, or retry
                        if confirm(new)==True: #confirm, update query index and exit
                            cf.modconfig(cf.modes[cf.mode],{qname:new})
                            return True
                        elif yesno('Try again?(y/n):')==False: #cancel
                            return True
                        else: #retry
                            continue
                    elif yesno('Description may not be blank.\nTry again?(y/n):')==False: #if entry empty string, cancel or...
                        return True
                    else: # retry
                        continue
            elif choice=='5': #Add new query
                addquery()
                return True
            elif choice=='6': #Remove query
                qname=qpick()
                cf.delconfig(qname)
                return True
            elif choice=='7': #Copy Query
                qname=qpick() #choose query to copy
                while True: #name new copy
                    new=raw_input("Enter name for copy:")
                    if new=='': #reject empty string
                        if yesno('Must enter a name.\nTry again?(y/n):')==True: #re-enter
                            continue
                        else: #or cancel
                            return True
                    elif (new in cf.options(cf.modes[cf.mode])) or (new in cf.sections()): #reject duplicate name
                        if yesno('May not overwrite existing query.\nTry again?(y/n):')==True: #re-enter
                            continue
                        else: #or cancel
                            return True
                    elif confirm(new)==True: #copy query
                        cf.addconfig(new,cf.get(cf.modes[cf.mode],qname))
                        if cf.has_option(qname,'sql'):
                            cf.set(new,'sql',cf.get(qname,'sql'))
                        print "Query '%s' copied as '%s'" % (qname,new)
                        return True
                    elif yesno('Try again?(y/n):')==True: #re-enter
                        continue
                    else: #or cancel
                        return True
            elif choice=='8': #Save configuration
                if save()==True:
                    cf.changessaved=True
                    print "Configuration saved."
                else:
                    print "CONFIGURATION NOT SAVED."
                return True
            elif choice=='9': #Finish and exit setup.
                if cf.consistant==False: #consistancy warning
                    if yesno('INDEX AND CONFIG SECTIONS STILL NOT MATCHED\nREPAIR BEFORE EXITING?(y/n):')==True: #fix inconsistency
                        cf.repair
                    else: #ignore inconsistency
                        print "Inconsistency ignored, may cause problems at runtime."
                else: #file consistent
                    pass
                if len(cf.empty)>0: #no SQL warning
                    if yesno('%s QUERIES HAVE NO SQL SET.\nEXIT ANYWAY(y/n):' % len(cf.empty))==False: #abort exit, return to menu
                        return True
                    else: #ignore empty sections
                        print "Empty sections ignored. Be sure to enter SQL before running queries."
                else: #SQL sections all populated
                    pass
                if cf.changessaved==False: #unsaved changes warning
                    while True: #save loop
                        if yesno('THERE ARE UNSAVED CHANGES.\nSAVE NOW?(y/n):')==True: #save before exiting
                            if save()==True: #save successful
                                cf.changessaved=True
                                print "Configuration saved."
                                break
                            else: #problem with save
                                print "CONFIGURATION NOT SAVED."
                        else: #do not save now
                            pass
                        if yesno('EXIT WITHOUT SAVING?(y/n)')==False: #abort exit and return to menu
                            return True
                        else: #exit without saving
                            print 'CHANGES DISCARDED'
                            break
                else: #no unsaved changes
                    pass
                return False #exit menu loop


        menuloop=True
        while menuloop==True: #menu loop
            if cf.consistant==True: #choices{} without repair
                choices={'1':'List queries','2':'Query detail view','3':'Edit query SQL','4':'Edit query description','5':'Add new query','6':'Remove query','7':'Copy Query','8':'Save configuration.','9':'Finished'}
                sort=range(1,10)
            else: #choices{} with repair
                choices={'0':'Repair index:section inconsistancies. (RECCOMENDED)','1':'List queries','2':'Query detail view','3':'Edit query SQL','4':'Edit query description','5':'Add new query','6':'Remove query','7':'Copy Query','8':'Save configuration.','9':'Finished'}
                sort=range(0,10)
            print "CHOOSE FROM THE OPTIONS BELOW"
            for option in sort: #show menu
                print "\t%s  %s" % (option,choices[str(option)])
            while True: #enter and confirm selection
                input=raw_input('Enter the number for your selection.\nCHOICE?:')
                try: #entry must be integer
                    choice=int(input)
                except:
                    print "Choice must be a number"
                    continue
                if input not in choices.keys():
                    print 'Invalid selection: %s' % input
                    continue
                else:
                    if confirm(choices[input])==False:
                        continue
                    else:
                        break
            menuloop=dochoice(input) # execute selected menu option. Breaks loop if finish operation confirmed
        return

    cf=handler() #Setup config file handler.  Creates new file if necessary.
    cf.changessaved=False
    if cf.newconfig==True: #For new config file, add queries
        addquery() #add new query sections.  Optionally entering SQL as well.
        if yesno("Save configuration now?(y/n):")==True: #save to file, then finish or continue
            if save()==True: #file saved successfully
                cf.consistant=True #checked later by repair and exit routines
                while True: #finished or continue working
                    answer=raw_input("Enter 'f' if finished, or 'c' to continue working.\nCHOICE?(f/c):")
                    if answer.lower() not in ('f','c','finished','continue'): #reject invalid response
                        print 'Invalid entry.'
                        continue
                    else: #answer valid
                        break
                if answer.lower()[0]=='f': #exit function
                    print '\n\n**********QUERY FILE SETUP OVER**********\n\n'
                    return
        else:
            cf.newconfig=False

    else: #for existing config file, check for problems
        if cf.consistant==True: #if query sections match, move on
            pass
        else: # if not, offer to repair
            if yesno("File index and configuration secton do not match.\nREPAIR NOW?(y/n):")==True:
                cf.repair
        while len(cf.empty)>0: #check for query sections without SQL
            print "The following queries are unconfigured:"
            for config in cf.empty: #list empties
                print "Name: %s\t Description: %s" % (config,cf.get(cf.modes[cf.mode],config))
            if yesno("Do you wish to edit them now?(y/n):")==False: #ignore empties and move on
                break
            else: # View empties and enter SQL
                for config in cf.empty: #show menu of empties
                    print "UNCONFIGURED QUERIES:"
                    print trim80("%s %s\t%s" % (str(cf.empty.index(config)+1),config,cf.get(self.modes[self.mode],config)))
                while True: #select query to edit.
                    choice=raw_input("Enter the number for the query you wish to edit.\nCHOICE:")
                    try: #test for valid integer input
                        if int(choice) not in range(1,(len(cf.empty)+2)): # reject numbers not on menu
                            print 'Invalid entry.'
                            continue
                        else: #if good choice
                            if confirm(cf.empty[int(choice)-1])==True: #confirm input
                                break
                            else:
                                continue
                    except: #reject non-integer input
                        print 'Invalid entry.'
                        continue
                while True: #editor loop
                    if editquery(cf.empty[int(choice)-1])==True: #SQL entry successful, exit edit sub-loop
                        cf.empty.remove(cf.empty[int(choice)-1])
                        print ("Query configured.")
                        break
                    else: #SQL entry failed. try again?
                        if yesno("Problem entering SQL.\nTry again?(y/n):")==True: #retry entry
                            continue
                        else: #exit edit sub-loop
                            break














    menu() # Run menu interface to manage query configs.
    print '\n\n**********QUERY FILE SETUP OVER**********\n\n'


                






#ODBC Connection object
#CSV File Writer
#class OutputFile(csv.writer):
#    def __init__(self,file,delimiter=',',quotechar='''"''',quoting=csv.QUOTE_MINIMAL):
#        self.writer=csv.writer(open(file,'w'),delimiter=delimiter,quotechar=quotechar,quoting=quoting):
#        self.rownums=rownums
#    def self.write(self,rows,headers=[]):
#        if self.writer.writerows(rows.append(headers))
#




#Option Parser
#query setup function
#download setup function

############ Main Block ###########
#if __name__==__main__:
querysetup()
    #check for command line flags, handle if present
    #open queries
    #open settings
    #check query hashes
    #run all or specified download profiles
        #get settings
        #get query
        #execute query
        #write data to file
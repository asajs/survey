import requests
import json
import sys
import re
import argparse
import csv

# I'm making the bad assumption that the data center won't change.
# It will, and it will break this tool when it does
# TODO: make it a commandline argument that defaults to az1
data_center = "az1"


def get_args(args):
    # Set up variables for access later
    api_token = None
    survey_token = None

    # They supplied a survey id and API token in the command line, override any file passed in
    if args.s is not None and args.t is not None:
        survey_token = str(args.s)
        api_token = str(args.t)
    elif args.f is not None:  # Read in the information from the file
        try:
            with open(args.f, 'r') as tfile:
                data = tfile.read().split("\n")
                if data[0][0:2] == "SV":
                    survey_token = str(data[0])
                    api_token = str(data[1])
                elif data[1][0:2] == "SV":
                    survey_token = str(data[1])
                    api_token = str(data[0])
                else:
                    print("Unable to read file " + args.f + ", does not appear to be formatted as expected.")
                    sys.exit()
        except IOError:
            print("Could not read token file " + str(args.f))
            sys.exit()
    else:  # They didn't supply the right arguments. Let them know and quit.
        print("API Token and Survey ID required")
        sys.exit()

    # location of our file
    location = None

    # if a parameter was passed in
    if args.d is not None:
        location = args.d
    else:
        print("No embedded data file passed in commandline. Data file path is required")
        sys.exit()

    return api_token, survey_token, location


def read_file(location):
    # default value is blank
    students = []

    # Attempt to open data file as a csv file
    if location[-4:] == ".csv":
        try:
            with open(location, 'r') as file:
                csvfile = csv.reader(file)
                for studentName in csvfile:
                    if studentName[0] != 'Name':
                        students.append(studentName[0])

        except IOError:
            print("Could not read file: " + str(location))
            sys.exit()

    # If it isn't a csv file, open it as a text file.
    else:
        try:
            with open(location, 'r') as file:
                students = file.read().split("\n")
                for i, s in enumerate(students):
                    if s.strip():
                        # The regex handles multi name students. The expected format is: "<one or more names>, <name>"
                        students.append(re.search('(\w+\s*)+, \w+', s).group(0))

        except IOError:
            print("Could not read file: " + str(location))
            sys.exit()

    # Alphabetize students
    students.sort()
    return students


def send_data(students, survey_token, api_token):
    length = len(students)

    keys = range(length)

    response = {}
    studentList = []
    j = 1

    # Store all students in required format for embedded data
    for i in keys:
        studentList.append({"key": "student" + str(j), "value": students[i], "type": "text"})
        j += 1

    # Prepare it for send off
    response["embeddedDataFields"] = studentList
    postSurvey = "https://byui.{0}.qualtrics.com/API/v3/surveys/{1}/embeddeddatafields".format(data_center, survey_token)

    postHeaders = {
        "x-api-token": api_token,
        "Content-Type": "application/json"
    }

    # Send data off and get response
    postResponse = requests.post(postSurvey, headers=postHeaders, data=json.dumps(response))

    responseString = postResponse.json()['meta']

    # If successful, say so. If not, print error response
    if responseString['httpStatus'] == '200 - OK':
        print("Successfully submitted embedded data")
    else:
        print("Error: " + responseString['httpStatus'])
        print("Error message: " + responseString['error']['errorMessage'])


def main(args):
    api_token, survey_token, location = get_args(args)
    students = read_file(location)
    send_data(students, survey_token, api_token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send embedded data to a Qualtrics survey')
    parser.add_argument('-d', type=str, help='The file where the embedded data is stored. (Required)', required=True)
    parser.add_argument('--s', type=str, help='The survey ID. (Required, or the --f option)')
    parser.add_argument('--t', type=str, help="The API token from Qualtrics. (Required, or the --f option)")
    parser.add_argument('--f', type=str,
                        help='A file that contains the survey ID and the API token separated by newlines.'
                             ' This is for convenience in submitting a survey ID and API Token.')

    args = parser.parse_args()
    main(args)

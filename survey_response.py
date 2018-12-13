# Python 3

import requests
import zipfile
import io
import os
import datetime
import sys
import csv
import re
import argparse
import errno
import shutil


def read_args(args):
    """
    Get the api token and the survey token from the user input
    :param args:
    :return:
    api_token, survey_token
    """
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
                if data[0][0:2] == "SV":  # Is the survey id the first thing?
                    survey_token = str(data[0])
                    api_token = str(data[1])
                elif data[1][0:2] == "SV":  # or the second thing?
                    survey_token = str(data[1])
                    api_token = str(data[0])
                else:  # If neither, quit.
                    print("Unable to read file " + args.f + ", does not appear to be formatted as expected.")
                    sys.exit()
        except IOError:
            print("Could not read token file " + str(args.f))
            sys.exit()
    else:  # They didn't supply the right arguments. Let them know and quit.
        print("API Token and Survey ID required")
        sys.exit()

    return api_token, survey_token


def download_file(api_token, survey_token):
    """
    Download the survey results from Qualtrics
    :param api_token:
    :param survey_token:
    :return:
    A zipped file of the survey results
    """
    # Setting user Parameters
    file_format = "csv"
    # For BYU-I the data center won't change (Questionable assumption. What about online students?)
    data_center = "az1"
    # Setting static parameters
    request_check_progress = 0
    progress_status = "in progress"
    base_url = "https://{0}.qualtrics.com/API/v3/responseexports/".format(data_center)
    headers = {
        "content-type": "application/json",
        "x-api-token": api_token,
        "Cache-Control": 'no-cache'
        }

    # Step 1: Creating Data Export
    download_request_url = base_url
    download_request_payload = '{"format":"' + file_format + '","surveyId":"' + survey_token + '"}'
    download_request_response = requests.request("POST", download_request_url, data=download_request_payload, headers=headers)
    progress_id = download_request_response.json()["result"]["id"]
    print("Website response: " + str(download_request_response.json()["meta"]["httpStatus"]))

    # Step 2: Checking on Data Export Progress and waiting until export is ready
    while request_check_progress < 100 and progress_status is not "complete":
        request_check_url = base_url + progress_id
        request_check_response = requests.request("GET", request_check_url, headers=headers)
        request_check_progress = request_check_response.json()["result"]["percentComplete"]
        print("Download is " + str(request_check_progress) + " complete")

    # Step 3: Downloading file
    request_download_url = base_url + progress_id + '/file'
    request_download = requests.request("GET", request_download_url, headers=headers, stream=True)

    return request_download


def unzip_file(request_download):
    """
    Unzip the file
    :param request_download:
    :return:
    return the zipped file and the path to it
    """
    zipped_file = zipfile.ZipFile(io.BytesIO(request_download.content))
    zip_file_path = zipped_file.extract(zipped_file.namelist()[0])
    print('Completed unzipping file')
    return zipped_file, zip_file_path


def rename_zipped(zipped_file):
    """
    Append the current date stamp to the filename to make it a little more unique
    :param zipped_file:
    :return:
    The old file name and the new file name.
    """
    # Get the path
    filename = zipped_file.namelist()[0]
    path = os.path.dirname(os.path.abspath(filename))

    # Remove spaces from the file name
    file_name = os.path.splitext(filename.replace(" ", ""))[0]

    # Add a datestamp to the file
    date = datetime.date.today()
    date_path = file_name + '_' + str(date.day) + '_' + str(date.month) + '_' + str(date.year) + '.csv'

    try:
        # rename the file, overwriting it in the process.
        os.replace(os.path.join(path, filename), os.path.join(path, date_path))
    except OSError:
        print("An error occurred in renaming the file.")
        raise

    print('Renamed file to ' + date_path)
    return file_name, date_path


def parse_file(file_name_date):
    """
    Collect all of the information from the reviews and organize it under the student
    :param file_name_date:
    :return:
    The parsed list
    """
    info = {}
    parsed_list = []
    order = []
    structure = []

    start_student = 14  # This magical number is the number of cells away from the first "studentXX".
    i = start_student
    j = 0  # Used in getting data into a position that makes sense.
    r = 0  # Row we currently are on
    tmp = 0  # Used in getting the number for the student
    try:
        with io.open(file_name_date, 'r', encoding="utf-8") as f:
            print("Opening file " + file_name_date + " for parsing")
            reader = csv.reader(f)
            for row in reader:
                if r == 0:
                    # The first thing we need to do is get the headers, or question names, whatever you want to call it.
                    # We are assuming the first question after the from studentxx is going to be select student.
                    # Continue until three before the end. The last three indexes are going to be location data.
                    while 'student' in str(row[i]):
                        i += 1
                    # We have reached the end of the studentxx format. Continue one past that.
                    i += 1
                    while i < len(row) - 3:
                        if '_' in str(row[i]):
                            structure.append(str(row[i]).split('_')[0])
                        else:
                            structure.append(str(row[i]))
                        i += 1

                    # We now have all of the appropriate headers. Start over at the right place and get the student
                    # id's.
                    i = start_student
                    # Get the student id's and have each one of them be assigned the structure of the info
                    while i < len(row) - 10:
                        info[row[i]] = {'first': '', 'last': ''}
                        for key in structure:
                            info[row[i]].update({key: []})
                        info[row[i]].update({'count': 0})

                        order.append(row[i])
                        i += 1
                elif r == 3:
                    # Reset magic number
                    i = start_student
                    while i < len(row) - 10:
                        # Just in case a student id, Ex student1, is actually a blank name.
                        # This prevents it from breaking and makes it more clear what happened.
                        # Honestly this should never happen, but it did at least once
                        if not row[i]:
                            row[i] = "BLANK, BLANK"
                        # Insert first and last names
                        info[order[j]]['first'] = re.split(", ", row[i])[1]
                        info[order[j]]['last'] = re.split(", ", row[i])[0]
                        i += 1
                        j += 1
                        tmp = i
                elif r > 3:
                    # Insert the data from the csv file
                    i = len(row) - 9
                    for key in structure:
                        try:
                            # Catch those that are integers or floats
                            float(row[i])
                            # use -1 as a marker for those who don't leave reviews
                            info['student' + str(row[tmp])][key].append(row[i] if row[i] else '-1')
                        except ValueError:
                            # Catch those that are strings, but ignore blank strings
                            if row[i].strip():
                                info['student' + str(row[tmp])][key].append(row[i])
                        i += 1

                    # Count the number of times a student has been rated to catch suspiciously high number of reviews.
                    info['student' + str(row[tmp])]['count'] += 1
                r += 1

            for student in info:
                # Create list of information for writing to file
                temp_variables = []
                temp_averages = []
                temp_strings = []
                tmp_list = [info[student]['last'], info[student]['first']]

                for key in structure:
                    try:
                        # Attempt to change the first item to an int. If it fails, than we know it isn't a list
                        # of integers. If it succeeds, than we do know it is a list of integers
                        int(info[student][key][0])
                        # If the int is less than zero it means it wasn't entered into the survey and should be ignored.
                        temp = [int(item) for item in info[student][key] if int(item or -1) >= 0]
                        temp_variables.append(temp)
                        average = None
                        if len(temp) > 0:
                            average = round(sum(temp) / float(len(temp)), 2)
                        temp_averages.append(average)
                    except (ValueError, IndexError) as e:
                        # Simply append anything that isn't a list of integers
                        temp_strings.append(info[student][key])

                # Count of reviews. This is to catch suspiciously high reviews
                tmp_list.append(info[student]['count'])

                # Total
                tmp_list.append(str(round(sum(temp_averages), 1)))

                # Add the averages
                tmp_list += [str(average) for average in temp_averages]

                # Add the comments
                tmp_list += temp_strings

                # Is there really information here?
                substance = False

                # List of review scores for individual
                for list_variables in temp_variables:
                    tmp_list.append(list_variables)
                    if len(list_variables) > 0:
                        substance = True

                # Check to see if there is anything in here besides a name.
                # This avoids students who haven't been reviewed.
                if substance:
                    parsed_list.append(tmp_list)
        f.close()
    except OSError:
        print("Failed to open file " + file_name_date + ".")
        raise

    print("Parsed " + str(file_name_date))
    # Sort list
    parsed_list.sort(key=lambda sort: sort[0])
    return parsed_list, structure


def make_directory(file_name):
    """
    Make a directory for this survey
    :param file_name:
    :return:
    """
    try:
        os.mkdir(file_name)
    except OSError as e:
        # If error is caused because it already exists, than do nothing. Else, crash the program.
        if e.errno != errno.EEXIST:
            raise


def change_directory(file_name, file_name_date):
    """
    Change into this survey directory and move the downloaded file into this directory
    :param file_name:
    :return:
    """
    print("Entering directory " + str(file_name))
    try:
        # Get directory BEFORE we change directories
        dir_path = os.path.dirname(os.path.realpath(__file__))
        # Get the full path to the downloaded file
        src = os.path.join(dir_path, file_name_date)
        dst = os.path.join(dir_path, file_name)
        # Change into the new directory
        os.chdir(file_name)
        # Move file_name_date into the new directory, overwriting it if it is already there.
        shutil.move(src, os.path.join(dst, file_name_date))
    except WindowsError:
        print("Failed to enter directory. Exiting")
        raise
    except OSError:
        print("Failed to enter directory. Exiting")
        raise


def write_student_file(parsed_list, structure):
    """
    Write out each students score and feedback into their own file
    :param parsed_list:
    :return:
    """
    student_file = ""
    # offset for i so we can skip what we have already printed: 'First', 'Last', 'Reviewed Counted', and 'Total'
    offset = 4
    print("Starting to write individual student files...")
    for student in parsed_list:
        try:
            # Each student file is named after them.
            student_file = str(student[0]) + "_" + str(student[1]) + ".txt"
            if not os.path.isfile(student_file):
                #io.open because we need the encoding to be utf-8, and io.open allows us to specify it.
                with io.open(student_file, "w", encoding="utf-8") as file:
                    # The students name, first then last
                    file.write(str(student[1]) + " " + str(student[0]) + "\n\n")
                    file.write("Score and comments from your presentation:\n\n")
                    file.write("Total: " + str(student[3]) + "\n")
                    for i, key in enumerate(structure):
                        try:
                            # Use the same trick used in parse_text to tell the difference
                            # between the numbers and the comments
                            float(student[i + offset][0])
                            file.write(str(key) + ": " + str(student[i + offset]) + "\n")
                        except ValueError:
                            # A string, because it's not a float?
                            file.write("\n" + str(key) + ": \n")
                            for comment in student[i + offset]:
                                # Don't put in blank lines.
                                if comment.strip():
                                    file.write("\t" + str(comment) + "\n")

        except OSError:
            print("Failed to write student " + student_file + ".")
    print("Completed writing individual student files.")


def write_all_info(file_name, parsed_list, structure):
    """
    Write out all of the students information into one place
    :param file_name:
    :param parsed_list:
    :return:
    """
    date = datetime.date.today()
    output_file = file_name + '_' + str(date.day) + '_' + str(date.month) + '_' + str(date.year) + '_parsed' + '.csv'
    # This offset allows us to use i and skip 'Last', 'First', 'Reviewed Count', 'Total' which are already in the
    # header.
    offset = 4

    # Write data to file in readable format.
    try:
        # With io.open because the encoding must be utf-8, and io.open allows us to set it to that
        with io.open(output_file, "w", encoding="utf-8") as resultFile:
            print("Writing all student reviews to " + output_file + ".")
            wr = csv.writer(resultFile, delimiter=',', dialect='excel', lineterminator='\n')

            # Set up the header
            heading = ['Last', 'First', 'Reviewed Count', 'Total']

            # There is two parts to this next part. First we get the headers for the averages and the strings
            # Then we put in all the same headers for what was averaged but without 'avg' as we are putting in
            # the individual scores.

            for i, key in enumerate(structure):
                try:
                    # Get all of the headers that can be averaged. (The numerical responses)
                    float(parsed_list[0][i + offset])
                    heading.append(str(key) + " avg")
                except (ValueError, TypeError) as e:
                    # Get all of the string responses
                    heading.append(str(key))

            for i, key in enumerate(structure):
                try:
                    # Get the headers for the individual scores
                    float(parsed_list[0][i + offset])
                    heading.append(str(key))
                except (ValueError, TypeError) as e:
                    # ignore the strings
                    continue

            # Write the headers
            wr.writerow(heading)

            # Now write a student and all of the associated information
            for student in parsed_list:
                wr.writerow(student)
    except PermissionError:
        print("Permission to write denied. " + output_file + " is probably open somewhere.")
    except OSError:
        print("Failed to write file " + output_file + ".")
        raise


def main(args):
    api_token, survey_token = read_args(args)
    downloaded_file = download_file(api_token, survey_token)
    zip_file, zip_path = unzip_file(downloaded_file)
    file_name, file_name_date = rename_zipped(zip_file)
    parsed_list, structure, = parse_file(file_name_date)
    make_directory(file_name)
    change_directory(file_name, file_name_date)
    write_student_file(parsed_list, structure)
    write_all_info(file_name, parsed_list, structure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get and parse data from a Qualtrics survey of students reviews')
    parser.add_argument('--s', type=str, help='The survey ID. (Required, or the --f option)')
    parser.add_argument('--t', type=str, help="The API token from Qualtrics. (Required, or the --f option)")
    parser.add_argument('--f', type=str,
                        help='A file that contains the survey ID and the API token separated by newlines.'
                             ' This is for convenience in submitting a survey ID and API Token.')
    args = parser.parse_args()
    main(args)

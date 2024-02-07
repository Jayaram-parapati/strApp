import logging, glob, os, time, requests, subprocess, io,shutil,tempfile

# from doc2pdf import convert,get_office_cli_path
from dotenv import load_dotenv
from pymongo import MongoClient
from mongoservice.conversion import CONVConnector
from urllib.parse import quote
from s3service.app import AWS_Boto3Service
from extractor import Autoextract


class Autoconvert:
    def __init__(self):
        log_filename = os.getenv("log_filename_autoconvert")
        self.aws_boto3_service = AWS_Boto3Service()
        self.convconnector = CONVConnector()
        logging.basicConfig(
            format="[%(asctime)s] :: %(levelname)s :: %(funcName)s :: %(lineno)d :: %(message)s",
            level=logging.DEBUG,
            filename=log_filename,
            filemode="a",
        )
        self.extraction = Autoextract()

    def autoconvert(self, s3_key, file_obj_id):
        try:
            file = os.path.basename(s3_key)
            fname, ext = os.path.splitext(file)
            new_s3_key = s3_key + ".pdf"
            ext = ext.lower()
            self.final_s3key = s3_key
            self.file_obj_id = file_obj_id
            logging.info(
                "[Batch Auto Convert] Started Processing S3 : {}".format(s3_key)
            )
            if ext != ".pdf":
                logging.info(
                    "[Batch Auto Convert] conversion started :{} ".format(file)
                    + "into{}".format(file + ".pdf")
                )
                
                print('newS3Key',new_s3_key)
                os.makedirs("temp", exist_ok=True)
                file_body = self.aws_boto3_service.get_file_obj(s3_key)
                # Use io.BytesIO to create in-memory streams
                temp_input_File = os.path.join('temp',file) #f"temp/{file}"
                temp_output_File = os.path.join('temp',f"{file}.pdf") #f"temp/{file}.pdf"
                # passing file name it require to save file
                with open(temp_input_File, "wb") as f:
                    f.write(file_body)
                self.convert2pdf(temp_input_File, temp_output_File)
                uploadfile_bytes = open(temp_output_File, 'rb')
                self.aws_boto3_service.upload_to_s3_file(new_s3_key, temp_output_File,uploadfile_bytes)
                res = self.convconnector.update_file(file_obj_id, s3_key, new_s3_key)
                print('Conversion done file update saved',res)
                os.remove(temp_input_File)
                os.remove(temp_output_File)
                self.final_s3key = new_s3_key

        except Exception as e:
            print("exception", e)

        finally:
            self.batch_autoconvert_finished()

    # def batch_autoconvert_finished(self):
    #     logging.info("[Batch Auto Convert] Finished")
    #     # TODO: Create async task to call extraction servce
    #     self.extraction.get_entities_from_s3key(self.final_s3key, self.file_obj_id)

    def convert2pdf(self, in_file, out_file=None):
        try:
            """Converts a file to PDF.

            Args:
                in_file (str): The path to the input file.
                out_file (str): The path to the output file, same path to in_file if not passes.
            """
            
            if not out_file:
                outdir = os.path.dirname(in_file)
            else:
                outdir = tempfile.gettempdir()
            
            
            subprocess.call([
                "soffice", 
                # '--headless',
                '--convert-to',
                'pdf',
                '--outdir', 
                outdir,
                in_file
            ])
            
            if out_file:
                out_temp_file_arr = os.path.splitext(in_file)
                out_temp_file_name =  f'{os.path.basename(out_temp_file_arr[0])}.pdf'
                out_file = f'{os.path.splitext(out_file)[0]}.pdf'
                shutil.move(os.path.join(outdir, out_temp_file_name), out_file)
            
            return os.path.join(outdir, out_temp_file_name)
        except Exception as ex:print('exxception convert2pdf', ex)

    # def preInitiate(tmp):
    #     initiate = Autoconvert()
    #     initiate.autoconvert(tmp)


# initiate = Autoconvert()
# initiate.autoconvert("C:\\Users\\prakash.vatala\\Pictures\\test1.jpg")
# while True:
#     initiate.autoconvert()
#     time.sleep(120)


# Convert DOC to PDF using LibreOffice in memory
# libreoffice_path = get_office_cli_path() #r"C:\Program Files\LibreOffice\program\soffice.exe"
# print('libreoffice_path',libreoffice_path)
# libreoffice_command = [
#     libreoffice_path,
#     '--headless',
#     '--convert-to', 'pdf',
#     '/dev/stdin',             #'/dev/stdin',  # Read from  ( use /dev/stdin for linux & CON for windows)
#     '--outdir', '/dev/stdout',      #'/dev/stdout',  # Write to stdout ( use /dev/stdout for linux & CON for windows)
# ]
# try:
#     p = subprocess.Popen(libreoffice_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#     process, err = p.communicate(file_body)
#     rc = p.returncode
#     print('rc',rc)
#     print(process)
# Run the LibreOffice command and capture stdout
# process = subprocess.run(libreoffice_command, input=input_stream.read(), check=True,capture_output=True)
# Get the converted PDF content from the output stream
# process = subprocess.run(libreoffice_command, input=file_body, stdout=subprocess.PIPE, check=True,capture_output=True)
#     pdf_content = process
# except subprocess.CalledProcessError as e:
#     print(f"Error running LibreOffice command: {e}")
#     pdf_content = b''

# pdf_content = subprocess.run(libreoffice_command, input=file_body, stdout=subprocess.PIPE, check=True).stdout


# status = True


#  to restart the libre office if it got stuck or not open
# "%ProgramFiles%\LibreOffice\program\soffice" --safe-mode
#  run the above command in run
#  And then hit enter.
# Now, click on Continue in Safe Mode and see if it works. If LibreOffice opens up fine, then you can close LibreOffice. And try to open normally, i.e. via your usual shortcut or icon method.
# If it doesn’t work, continue to the next step.

#  check the link ==>  https://www.libreofficehelp.com/fix-cant-open-libreoffice/#:~:text=In%20Windows%2C%20open%20Task%20Manager,and%20try%20to%20open%20it.

import os

class uploadfile():
    def __init__(self, name, type=None, size=None, not_allowed_msg='', hash='', original_name=None):
        self.name = name
        self.type = type
        self.size = size
        self.not_allowed_msg = not_allowed_msg
        self.url = "data/%s" % name
#         self.delete_url = "delete/%s" % name
        self.delete_type = "DELETE"
        self.status_id = str(name)+"_btn" 
        self.hash = hash
        self.original_name = original_name

    def get_file(self):
        if self.type != None:          
            # POST an normal file
            if self.not_allowed_msg == '':
                return {"name": self.name,
                        "type": self.type,
                        "size": self.size, 
                        "url": self.url,
                        "status_id":self.status_id,
                        "original_name": self.original_name,
#                         "deleteUrl": self.delete_url, 
                        "deleteType": self.delete_type,}

            # File type is not allowed
            else:
                return {"error": self.not_allowed_msg,
                        "name": self.name,
                        "type": self.type,
                        "size": self.size,}

     
        # GET normal file from disk
        else:
            return {"name": self.name,
                    "size": self.size, 
                    "url": self.url,
                    "status_id":self.status_id,
                    "original_name": self.original_name,
#                     "deleteUrl": self.delete_url, 
                    "deleteType": self.delete_type,}

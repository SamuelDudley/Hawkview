# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Based on Eli Bendersky's PyCrypto example at
# http://eli.thegreenplace.net/2010/06/25/
#     aes-encryption-of-files-in-python-with-pycrypto
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

import os
import struct
from Crypto import Random
from Crypto.Cipher import AES

AES_MODE = AES.MODE_CBC
IVEC_SIZE = 16

DEFAULT_CHUNKSIZE = 64 * 1024
FILE_LENGTH_FIELD_SIZE = struct.calcsize('Q')

OUTPUT_FILE_DEFAULT_SUFFIX = '.enc'

# Indicator for moving file pointer relative to end of file.
WHENCE_EOF = 2


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def encrypt_file(
        key, in_filename, out_filename=None, chunksize=DEFAULT_CHUNKSIZE
        ):
    ''' Encrypts a file using AES (CBC mode) with the given key.

        Arguments:
            key (str):
                The encryption key - a string that must be either 16,
                24 or 32 bytes long. Longer keys are more secure.

            in_filename (str):
                Name of the input file.

            out_filename (str):
                Name of the output file. If None, '<in_filename>.enc'
                will be used.

            chunksize (int):
                Sets the size of the chunk which the function uses to
                read and encrypt the file. Larger chunk sizes can be
                faster for some files and machines. chunksize must be
                divisible by 16.

    '''
    if not out_filename:
        out_filename = in_filename + OUTPUT_FILE_DEFAULT_SUFFIX

    ivec = Random.new().read(IVEC_SIZE)
    encryptor = AES.new(key, AES_MODE, ivec)
    filesize = os.path.getsize(in_filename)

    file_length_field = struct.pack('<Q', filesize)

    with open(in_filename, 'rb') as infp:
        with open(out_filename, 'wb') as outfp:

            assert len(ivec) == IVEC_SIZE
            outfp.write(ivec)

            chunk = None
            final_chunk = False

            while True:

                # Encrypt the previous chunk, then read the next.
                if chunk is not None:
                    outfp.write(encryptor.encrypt(chunk))

                if final_chunk:
                    break

                chunk = infp.read(chunksize)

                # The first time we get anything other than a full
                # chunk, we've exhausted the input file and it's time
                # to add the padding and length indicator.
                if len(chunk) == 0 or len(chunk) % 16 != 0:

                    padding_size = (
                        16 - (len(chunk) + FILE_LENGTH_FIELD_SIZE) % 16
                        )
                    padding = ' ' * padding_size

                    chunk += padding
                    chunk += file_length_field
                    assert len(chunk) % 16 == 0

                    final_chunk = True


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def decrypt_file(key, in_filename, out_filename=None, chunksize=24 * 1024):
    ''' Decrypts a file using AES (CBC mode) with the given key.

        Parameters are similar to encrypt_file, with one difference:
        out_filename, if not supplied will be in_filename without its
        last extension (i.e. if in_filename is 'aaa.zip.enc' then
        out_filename will be 'aaa.zip')

    '''
    if not out_filename:
        out_filename = os.path.splitext(in_filename)[0]

    with open(in_filename, 'rb') as infp:

        ivec = infp.read(IVEC_SIZE)
        decryptor = AES.new(key, AES_MODE, ivec)

        with open(out_filename, 'wb+') as outfp:

            # We need to read the next chunk to know how to treat this
            # first chunk.
            chunk = infp.read(chunksize)
            final_chunk = False

            while True:

                # We need to read the new chunk to know how to treat
                # the current chunk.
                new_chunk = infp.read(chunksize)

                plaintext_chunk = decryptor.decrypt(chunk)

                if len(new_chunk) == 0:
                    final_chunk = True

                outfp.write(plaintext_chunk)

                if final_chunk:
                    # Read the expected file length from the now
                    # complete reconstruction of the original file.
                    # This moves the file pointer back from the end of
                    # the file then reads the same number of bytes
                    # back in, so should leave the file pointer at the
                    # same position, but we break out of the read loop
                    # anyway.
                    outfp.seek(-FILE_LENGTH_FIELD_SIZE, WHENCE_EOF)
                    file_length_field = outfp.read(FILE_LENGTH_FIELD_SIZE)
                    origsize = struct.unpack('<Q', file_length_field)[0]
                    break

                chunk = new_chunk

            outfp.truncate(origsize)
"""
Deuce API
"""
import datetime
import json
import requests
import logging
from urllib.parse import urlparse, parse_qs

import msgpack
from stoplight import validate

import deuceclient.api.afile as api_file
import deuceclient.api.block as api_block
import deuceclient.api.blocks as api_blocks
import deuceclient.api.storageblocks as api_storageblocks
import deuceclient.api.vault as api_vault
import deuceclient.api.v1 as api_v1
from deuceclient.common.command import Command
from deuceclient.common.validation import *
from deuceclient.common.validation_instance import *


class DeuceClient(Command):

    """
    Object defining HTTP REST API calls for interacting with Deuce.
    """

    def __init__(self, authenticator, apihost, sslenabled=False):
        """Initialize the Deuce Client access

        :param authenticator: instance of deuceclient.auth.Authentication
                              to use for retrieving auth tokens
        :param apihost: server to use for API calls
        :param sslenabled: True if using HTTPS; otherwise false
        """
        super(DeuceClient, self).__init__(apihost,
                                          '/',
                                          sslenabled=sslenabled)
        self.log = logging.getLogger(__name__)
        self.sslenabled = sslenabled
        self.authenticator = authenticator

    def __update_headers(self):
        """Update common headers
        """
        self.headers['X-Auth-Token'] = self.authenticator.AuthToken
        self.headers['X-Project-ID'] = self.project_id

    def __log_request_data(self, fn=None, headers=None):
        """Log the information about the request
        """
        if fn is not None:
            self.log.debug('Performing %s', fn)
        self.log.debug('host: %s', self.apihost)
        self.log.debug('body: %s', self.Body)
        if headers is None:
            self.log.debug('headers: %s', self.Headers)
        else:
            self.log.debug('headers: %s', headers)
        self.log.debug('uri: %s', self.Uri)

    def __log_response_data(self, response, jsondata=False, fn=None):
        """Log the information about the response
        """
        if fn is not None:
            self.log.debug('Response from %s', fn)

        self.log.debug('headers: %s', response.headers)
        self.log.debug('status: %s', response.status_code)
        self.log.debug('json data: %s', jsondata)
        if jsondata:
            try:
                self.log.debug('content: %s', response.json())
            except:
                self.log.debug('content: %s', response.text)
        else:
            if response.text:
                if len(response.text):
                    self.log.debug('content: %s', response.text)
                else:  # pragma: no cover
                    self.log.debug('content: zero-length')
            else:
                self.log.debug('content: NONE')

    @property
    def project_id(self):
        """Return the project id to use
        """
        return self.authenticator.AuthTenantId

    @validate(project=ProjectInstanceRule, marker=VaultIdRuleNoneOkay)
    def ListVaults(self, project, marker=None):
        """List vaults for the user
        :returns: deuceclient.api.Projects instance containing the vaults
        :raises: RuntimeError on failure
        """
        path = api_v1.get_vault_base_path()

        if marker is not None:
            self.ReInit(self.sslenabled,
                        '{0:}?marker={1:}'.format(path, marker))
        else:
            self.ReInit(self.sslenabled, path)

        self.__update_headers()
        self.__log_request_data(fn='List Vaults')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=True, fn='List Vaults')

        if res.status_code == 200:
            for vault_name, vault_data in res.json().items():
                if vault_name not in project:
                    project[vault_name] = api_vault.Vault(
                        project_id=project.project_id,
                        vault_id=vault_name)
                    project[vault_name].status = 'valid'
            if 'x-next-batch' in res.headers:
                parsed_url = urlparse(res.headers['x-next-batch'])

                qs = parse_qs(parsed_url[4])
                project.marker = qs['marker'][0]
            else:
                project.marker = None

            return True
        else:
            raise RuntimeError(
                'Failed to List Vaults. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault_name=VaultIdRule)
    def CreateVault(self, vault_name):
        """Create a vault

        :param vault_name: name of the vault

        :returns: deuceclient.api.Vault instance of the new Vault
        :raises: TypeError if vault_name is not a string object
        :raises: RunTimeError on failure
        """
        path = api_v1.get_vault_path(vault_name)
        self.ReInit(self.sslenabled, path)

        self.__update_headers()
        self.__log_request_data(fn='Create Vault')
        res = requests.put(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Create Vault')

        if res.status_code == 201:
            vault = api_vault.Vault(project_id=self.project_id,
                                    vault_id=vault_name)
            vault.status = 'created'
            return vault
        else:
            raise RuntimeError(
                'Failed to create Vault. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault_name=VaultIdRule)
    def GetVault(self, vault_name):
        """Get an existing vault

        :param vault_name: name of the vault

        :returns: deuceclient.api.Vault instance of the existing Vault
        :raises: TypeError if vault_name is not a string object
        :raises: RunTimeError on failure
        """
        if self.VaultExists(vault_name):
            vault = api_vault.Vault(project_id=self.project_id,
                                    vault_id=vault_name)
            vault.status = 'valid'
            return vault
        else:
            raise RuntimeError('Failed to find a Vault with the name {0:}'
                               .format(vault_name))

    @validate(vault=VaultInstanceRule)
    def DeleteVault(self, vault):
        """Delete a Vault

        :param vault: the vault to be deleted

        :returns: True on success
        :raises: TypeError if vault is not a Vault object
        :raises: RunTimeError on failure
        """
        path = api_v1.get_vault_path(vault.vault_id)
        self.ReInit(self.sslenabled, path)
        self.__update_headers()
        self.__log_request_data(fn='Delete Vault')
        res = requests.delete(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Delete Vault')

        if res.status_code == 204:
            vault.status = 'deleted'
            return True
        else:
            raise RuntimeError(
                'Failed to delete Vault. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    def VaultExists(self, vault):
        """Return the statistics on a Vault

        :param vault: Vault object for the vault or name of vault to
                      be verified

        :returns: True if the Vault exists; otherwise False
        :raises: RunTimeError on error
        """
        # Note: We cannot use GetVault() here b/c it would
        #   end up being self-referential
        vault_id = vault
        if isinstance(vault, api_vault.Vault):
            vault_id = vault.vault_id

        path = api_v1.get_vault_path(vault_id)
        self.ReInit(self.sslenabled, path)
        self.__update_headers()
        self.__log_request_data(fn='Vault Exists')
        res = requests.head(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Vault Exists')

        if res.status_code == 204:
            if isinstance(vault, api_vault.Vault):
                vault.status = 'valid'
            return True
        elif res.status_code == 404:
            if isinstance(vault, api_vault.Vault):
                vault.status = 'invalid'
            return False
        else:
            raise RuntimeError(
                'Failed to determine if Vault exists. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule)
    def GetVaultStatistics(self, vault):
        """Retrieve the statistics on a Vault

        :param vault: vault to get the statistics for

        :store: The Statistics for the Vault in the statistics property
                for the specific Vault
        :returns: True on success
        :raises: TypeError if vault is not a Vault object
        :raises: RunTimeError on failure
        """
        path = api_v1.get_vault_path(vault.vault_id)
        self.ReInit(self.sslenabled, path)
        self.__update_headers()
        self.__log_request_data(fn='Get Vault Statistics')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=True, fn='Get Vault Statistics')

        if res.status_code == 200:
            vault.statistics = res.json()
            return True
        else:
            raise RuntimeError(
                'Failed to get Vault statistics. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              marker=MetadataBlockIdRuleNoneOkay,
              limit=LimitRuleNoneOkay)
    def GetBlockList(self, vault, marker=None, limit=None):
        """Retrieve the list of blocks in the vault

        :param vault: vault to get the block list for
        :param marker: marker denoting the start of the list
        :param limit: integer denoting the maximum entries to retrieve

        :stores: The block information in the blocks property of the Vault
        :returns: True on success
        :raises: TypeError if vault is not a Vault object
        :raises: RunTimeError on failure
        """
        url = api_v1.get_blocks_path(vault.vault_id)
        if marker is not None or limit is not None:
            # add the separator between the URL and the parameters
            url = url + '?'

            # Apply the marker
            if marker is not None:
                url = '{0:}marker={1:}'.format(url, marker)
                # Apply a comma if the next item is not none
                if limit is not None:
                    url = url + ','

            # Apply the limit
            if limit is not None:
                url = '{0:}limit={1:}'.format(url, limit)

        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Get Block List')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=True, fn='Get Block List')

        if res.status_code == 200:
            block_ids = []
            for block_entry in res.json():
                vault.blocks[block_entry] = api_block.Block(vault.project_id,
                                                            vault.vault_id,
                                                            block_entry)
                block_ids.append(block_entry)

            if 'x-next-batch' in res.headers:
                parsed_url = urlparse(res.headers['x-next-batch'])

                qs = parse_qs(parsed_url[4])
                vault.blocks.marker = qs['marker'][0]
            else:
                vault.blocks.marker = None

            return block_ids
        else:
            raise RuntimeError(
                'Failed to get Block list for Vault . '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              block=BlockInstanceRule)
    def HeadBlock(self, vault, block):
        """Head a block and get its information

        :param vault: vault to upload the block into
        :param block: block to be uploaded
                      must be deuceclient.api.Block type

        :returns: True on success
        """
        url = api_v1.get_block_path(vault.vault_id, block.block_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        headers = {}
        headers.update(self.Headers)
        headers['content-type'] = 'application/octet-stream'
        self.__log_request_data(headers=headers, fn='Head Block')
        res = requests.head(self.Uri, headers=headers)
        self.__log_response_data(res, jsondata=False, fn='Head Block')
        if res.status_code == 204:
            block.ref_modified = int(res.headers['X-Ref-Modified'])\
                if res.headers['X-Ref-Modified'] else 0

            block.ref_count = int(res.headers['X-Block-Reference-Count'])\
                if res.headers['X-Block-Reference-Count'] else 0

            block.block_size = int(res.headers['X-Block-Size'])\
                if res.headers['X-Block-Size'] else 0

            block.storage_id = None if res.headers['X-Storage-ID'] == \
                'None' else res.headers['X-Storage-ID']

            # Any block we get back here cannot be orphaned
            block.block_orphaned = False
            return block
        else:
            raise RuntimeError(
                'Failed to Head Block {0:} in Vault {1}:. '
                'Error ({2:}): {3:}'.format(block.block_id, vault.vault_id,
                                            res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              block=BlockInstanceRule)
    def UploadBlock(self, vault, block):
        """Upload a block to the vault specified.

        :param vault: vault to upload the block into
        :param block: block to be uploaded
                      must be deuceclient.api.Block type

        :returns: True on success
        """
        url = api_v1.get_block_path(vault.vault_id, block.block_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        headers = {}
        headers.update(self.Headers)
        headers['content-type'] = 'application/octet-stream'
        headers['content-length'] = len(block)
        self.__log_request_data(headers=headers, fn='Upload Block')
        res = requests.put(self.Uri, headers=headers, data=block.data)
        self.__log_response_data(res, jsondata=False, fn='Upload Block')
        if res.status_code == 201:
            return True
        else:
            raise RuntimeError(
                'Failed to upload Block. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              block_ids=MetadataBlockIdIterableRule)
    def UploadBlocks(self, vault, block_ids):
        """Upload a series of blocks at the same time

        :param vault: vault to upload the blocks into
        :param block_ids: block ids in the vault to upload,
                          must be an iterable object
        :returns: True on success
        """
        url = api_v1.get_blocks_path(vault.vault_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        headers = {}
        headers.update(self.Headers)
        headers['Content-Type'] = 'application/msgpack'

        block_data = []
        for block_id in block_ids:
            block = vault.blocks[block_id]

            block_data.append((block_id, block.data))

        contents = dict(block_data)
        body = msgpack.packb(contents)
        self.__log_request_data(fn='Upload Multiple Blocks - msgpack')
        res = requests.post(self.Uri, headers=headers, data=body)
        self.__log_response_data(res,
                                 jsondata=False,
                                 fn='Upload Multiple Blocks - msgpack')
        if res.status_code == 201:
            return True
        else:
            raise RuntimeError(
                'Failed to upload blocks to Vault. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              block=BlockInstanceRule)
    def DeleteBlock(self, vault, block):
        """Delete the block from the vault.

        :param vault: vault to delete the block from
        :param block: the block to be deleted

        :returns: True on success

        Note: The block is not removed from the local Vault object
        """
        url = api_v1.get_block_path(vault.vault_id, block.block_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Delete Block')
        res = requests.delete(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Delete Block')
        if res.status_code == 204:
            return True
        else:
            raise RuntimeError(
                'Failed to delete Vault. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule, block_ids=MetadataBlockIdIterableRule)
    def DeleteBlocks(self, vault, block_ids):
        """Delete a list of blocks from the vault.

        :param vault: vault to upload the blocks into
        :param block_ids: block ids in the vault to upload,
                          must be an iterable object
        :returns: list of tuples of the block id and a boolean to denote the
                  result of its deletion
        """
        def do_delete_block(block_id):
            try:
                return (block_id, self.DeleteBlock(vault,
                                                   vault.blocks[block_id]))
            except Exception as ex:
                self.log.debug('Delete Blocks: Failed to delete block '
                               '({0}) - Exception {1}'.format(block_id,
                                                              str(ex)))
                return (block_id, False)
        return [do_delete_block(blockid) for blockid in block_ids]

    @validate(vault=VaultInstanceRule,
              block=BlockInstanceRule)
    def DownloadBlock(self, vault, block):
        """Gets the data associated with the block id provided

        :param vault: vault to download the block from
        :param block: the block to be downloaded

        :stores: The block Data in the the data property of the block
        :returns: True on success
        """
        url = api_v1.get_block_path(vault.vault_id, block.block_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Download Block')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Download Block')

        if res.status_code == 200:
            block.data = res.content
            return True
        else:
            raise RuntimeError(
                'Failed to get Block Content for Block Id . '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule)
    def CreateFile(self, vault):
        """Create a file

        :param vault: vault to create the file in
        :returns: create an object for the new file and adds it to the vault
                  and then return the name of the file within the vault
        """
        url = api_v1.get_files_path(vault.vault_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Create File')
        res = requests.post(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Create File')
        if res.status_code == 201:
            new_file = api_file.File(project_id=self.project_id,
                                     vault_id=vault.vault_id,
                                     file_id=res.headers['x-file-id'],
                                     url=res.headers['location'])
            vault.files[new_file.file_id] = new_file
            return new_file.file_id
        else:
            raise RuntimeError(
                'Failed to Create File. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              file_id=FileIdRule)
    def DeleteFile(self, vault, file_id):
        """Delete a file

        :param vault: vault to download the file from
        :param file_id: file id within the vault to be deleted
        """
        url = api_v1.get_file_path(vault.vault_id, file_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Delete File')
        res = requests.delete(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=False, fn='Delete File')
        if res.status_code == 204:
            return True
        else:
            raise RuntimeError(
                'Failed to Delete File. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              file_id=FileIdRule)
    def DownloadFile(self, vault, file_id, output_file, chunk_size=512 * 1024):
        """Download a file

        :param vault: vault to download the file from
        :param file_id: file id within the vault to download
        :param output_file: local fully qualified (absolute) file name to
                            store the file in
        :returns: True on success
        """
        url = api_v1.get_file_path(vault.vault_id, file_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Download File')
        res = requests.get(self.Uri, headers=self.Headers, stream=True)
        if res.status_code == 200:
            try:
                downloaded_bytes = 0
                download_start_time = datetime.datetime.utcnow()
                with open(output_file, 'wb') as output:
                    for chunk in res.iter_content(chunk_size=chunk_size):
                        output.write(chunk)
                        downloaded_bytes = downloaded_bytes + len(chunk)
                        res.raise_for_status()
                download_end_time = datetime.datetime.utcnow()

                download_time = download_end_time - download_start_time
                download_rate = downloaded_bytes / download_time\
                    .total_seconds()

                log = logging.getLogger(__name__)
                log.info('Downloaded {0:} bytes in {1:} seconds for {2:} bps, '
                         '{3:} kbps, {4:} mbps'
                         .format(downloaded_bytes, download_time,
                                 download_rate,
                                 download_rate / 1024,
                                 download_rate / 1024 / 1024))

                # succeeded in downloading the file
                return True

            except Exception as ex:
                raise RuntimeError(
                    'Failed while Downloading File. '
                    'Error: {0:} '.format(ex))
        else:
            raise RuntimeError(
                'Failed to Download File. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              file_id=FileIdRule)
    def FinalizeFile(self, vault, file_id):
        """Finalize the file in the vault

        :param vault: vault containing the file
        :param file_id: file_id of the file to finalize

        :returns: True on success
        """
        if file_id not in vault.files:
            raise KeyError('file_id must specify a file in the provided Vault')

        url = api_v1.get_file_path(vault.vault_id, file_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        headers = {}
        headers.update(self.Headers)
        headers['X-File-Length'] = len(vault.files[file_id])
        self.__log_request_data(fn='Finalize File')
        res = requests.post(self.Uri, headers=headers)
        self.__log_response_data(res, jsondata=True, fn='Finalize File')
        if res.status_code in (200, 204):
            return True
        else:
            raise RuntimeError(
                'Failed to finalize file. Details: {0}'
                .format(res.json()))

    @validate(vault=VaultInstanceRule,
              file_id=FileIdRule,
              block_ids=MetadataBlockIdOffsetIterableRuleNoneOkay)
    def AssignBlocksToFile(self, vault, file_id, block_ids=None):
        """Assigns the specified block to a file

        :param vault: vault to containing the file
        :param file_id: file_id of the file in the vault that the block
                        will be assigned to
        :param block_ids: optional parameter specify list of Block IDs that
                          have already been assigned to the File object
                          specified by file_id within the Vault in the form
                          [(blockid, offset)]
        :returns: a list of blocks id that have to be uploaded to complete
                  if all the required blocks have been uploaded the the
                  list will be empty.
        """
        if file_id not in vault.files:
            raise KeyError('file_id must specify a file in the provided Vault')
        if block_ids is not None:
            if len(block_ids) == 0:
                raise ValueError('block_ids must be iterable')
            for block_id, offset in block_ids:
                if str(offset) not in vault.files[file_id].offsets:
                    raise KeyError(
                        'block offset {0} must be assigned in the File'.
                        format(offset))
                if vault.files[file_id].offsets[str(offset)] != block_id:
                    raise ValueError(
                        'specified offset {0} must match the block {1}'.
                        format(offset, block_id))
        else:
            if len(vault.files[file_id].offsets) == 0:
                raise ValueError('File must have offsets specified')

        url = api_v1.get_fileblocks_path(vault.vault_id, file_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Assign Blocks To File')

        """
        File Block Assignment Takes a JSON body containing the following:
                [
                    [block_id, offset],
                    ...
                ]
        """
        block_assignment_data = []

        if block_ids is not None:
            block_assignment_data = [(block_id, offset)
                                     for block_id, offset in block_ids]
        else:
            block_assignment_data = [(block_id, offset)
                                     for offset, block_id in
                                     vault.files[file_id].offsets.items()]

        self.log.debug('Assigning blocks to offset:')
        for block_id, offset in block_assignment_data:
            self.log.debug('Offset, Block -> {0:}, {1:}'.format(offset,
                                                                block_id))

        res = requests.post(self.Uri,
                            data=json.dumps(block_assignment_data),
                            headers=self.Headers)
        self.__log_response_data(res, jsondata=True,
                                 fn='Assign Blocks To File')
        if res.status_code == 200:
            block_list_to_upload = [block_id
                                    for block_id in res.json()]
            return block_list_to_upload
        else:
            raise RuntimeError(
                'Failed to Assign Blocks to the File. '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule,
              file_id=FileIdRule,
              marker=MetadataBlockIdRuleNoneOkay,
              limit=LimitRuleNoneOkay)
    def GetFileBlockList(self, vault, file_id, marker=None, limit=None):
        """Retrieve the list of blocks assigned to the file

        :param vault: vault to the file belongs to
        :param fileid: fileid of the file in the Vault to list the blocks for
        :param marker: blockid within the list to start at
        :param limit: the maximum number of entries to retrieve

        :stores: The resulting block list in the file data for the vault.
        :returns: True on success
        """
        if file_id not in vault.files:
            raise KeyError(
                'file_id must specify a file in the provided Vault.')

        url = api_v1.get_fileblocks_path(vault.vault_id, file_id)

        if marker is not None or limit is not None:
            # add the separator between the URL and the parameters
            url = url + '?'

            # Apply the marker
            if marker is not None:
                url = '{0:}marker={1:}'.format(url, marker)
                # Apply a comma if the next item is not none
                if limit is not None:
                    url = url + ','

            # Apply the limit
            if limit is not None:
                url = '{0:}limit={1:}'.format(url, limit)

        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Get File Block List')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res, jsondata=True, fn='Get File Block List')

        if res.status_code == 200:
            block_ids = []
            for block_id, offset in res.json():
                vault.files[file_id].offsets[offset] = block_id
                block_ids.append(block_id)

            next_marker = None
            if 'x-next-batch' in res.headers:
                parsed_url = urlparse(res.headers['x-next-batch'])

                qs = parse_qs(parsed_url[4])
                next_marker = qs['marker'][0]

            return (block_ids, next_marker)
        else:
            raise RuntimeError(
                'Failed to get Block list for File . '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule, block=BlockInstanceRule)
    def DownloadBlockStorageData(self, vault, block):
        """Download a block directly from block storage

        :param vault: instance of deuce.api.vault.Vault
        :param block: instance of deuce.api.block.Block
        :return: instance of deuce.api.block.Block if expected
                 status code is returned, Runtime Error raised
                 if that's not the case.
        """
        url = api_v1.get_storage_block_path(vault.vault_id,
                                            block.storage_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Download Block Storage Data')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res,
                                 jsondata=False,
                                 fn='Download Block Storage Data')

        if res.status_code == 200:
            block.data = res.content
            block.ref_modified = int(res.headers['X-Ref-Modified'])\
                if res.headers['X-Ref-Modified'] else 0

            block.ref_count = int(res.headers['X-Block-Reference-Count'])\
                if res.headers['X-Block-Reference-Count'] else 0

            block.block_id = res.headers['X-Block-ID']
            return block
        else:
            raise RuntimeError(
                'Failed to get Content for Storage Block Id: {0:}, Vault: {1:}'
                'Error ({2:}): {3:}'.format(block.storage_id, vault.vault_id,
                                            res.status_code,
                                            res.text))

    @validate(vault=VaultInstanceRule, block=BlockInstanceRule)
    def DeleteBlockStorage(self, vault, block):
        """Delete a block directly from block storage

        :param vault: instance of deuce.api.vault.Vault
        :param block: instance of deuce.api.block.Block
        :return: True if expected status code is returned,
                 Runtime Error raised if that's not the case.
        """
        url = api_v1.get_storage_block_path(vault.vault_id,
                                            block.storage_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Delete Block Storage')
        res = requests.delete(self.Uri, headers=self.Headers)
        self.__log_response_data(res,
                                 jsondata=False,
                                 fn='Delete Block Storage')
        if res.status_code == 204:
            return True
        else:
            raise RuntimeError(
                'Failed to delete Block {0:} from BlockStorage, Vault {1:}'
                'Error ({2:}): {3:}'.format(block.storage_id, vault.vault_id,
                                            res.status_code,
                                            res.text))

    @validate(vault=VaultInstanceRule, marker=StorageBlockIdRuleNoneOkay,
              limit=LimitRuleNoneOkay)
    def GetBlockStorageList(self, vault, marker=None, limit=None):
        """List blocks directly from block storage

        :param vault: instance of deuce.api.vault.Vault
        :param marker: string
        :param limit: string
        :return: True if expected status code is returned,
                 Runtime Error raised if that's not the case.
        """
        url = api_v1.get_storage_blocks_path(vault.vault_id)
        if marker is not None or limit is not None:
            # add the separator between the URL and the parameters
            url = url + '?'

            # Apply the marker
            if marker is not None:
                url = '{0:}marker={1:}'.format(url, marker)
                # Apply a separator if the next item is not none
                if limit is not None:
                    url = url + '&'

            # Apply the limit
            if limit is not None:
                url = '{0:}limit={1:}'.format(url, limit)

        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Get Block Storage List')
        res = requests.get(self.Uri, headers=self.Headers)
        self.__log_response_data(res,
                                 jsondata=True,
                                 fn='Get Block Storage List')

        if res.status_code == 200:
            block_list = api_storageblocks.StorageBlocks(
                project_id=self.project_id,
                vault_id=vault.vault_id)
            blocks = {
                storageblockid: api_block.Block(project_id=self.project_id,
                                                vault_id=vault.vault_id,
                                                storage_id=storageblockid,
                                                block_type='storage')
                for storageblockid in res.json()}
            block_list.update(blocks)
            vault.storageblocks.update(block_list)

            if 'x-next-batch' in res.headers:
                parsed_url = urlparse(res.headers['x-next-batch'])

                qs = parse_qs(parsed_url[4])
                vault.storageblocks.marker = qs['marker'][0]
            else:
                vault.storageblocks.marker = None

            return [storageblockid for storageblockid in res.json()]
        else:
            raise RuntimeError(
                'Failed to get Block Storage list for Vault . '
                'Error ({0:}): {1:}'.format(res.status_code, res.text))

    @validate(vault=VaultInstanceRule, block=BlockInstanceRule)
    def HeadBlockStorage(self, vault, block):
        """Head a block directly from block storage

        :param vault: instance of deuce.api.vault.Vault
        :param block: instance of deuce.api.block.Block
        :return: instance of deuce.api.block.Block if expected
                 status code is returned, Runtime Error raised
                 if that's not the case.
        """

        url = api_v1.get_storage_block_path(vault.vault_id,
                                            block.storage_id)
        self.ReInit(self.sslenabled, url)
        self.__update_headers()
        self.__log_request_data(fn='Head Block in Storage')
        res = requests.head(self.Uri, headers=self.Headers)
        self.__log_response_data(res,
                                 jsondata=True,
                                 fn='Head Block in Storage')
        if res.status_code == 204:
            block.ref_modified = int(res.headers['X-Ref-Modified'])\
                if res.headers['X-Ref-Modified'] else 0

            block.ref_count = int(res.headers['X-Block-Reference-Count'])\
                if res.headers['X-Block-Reference-Count'] else 0

            block.block_id = None if res.headers['X-Block-ID'] == \
                'None' else res.headers['X-Block-ID']

            block.block_size = int(res.headers['X-Block-Size'])\
                if res.headers['X-Block-Size'] else 0

            block.block_orphaned = \
                json.loads(res.headers['X-Block-Orphaned'].lower())
            return block
        else:
            raise RuntimeError(
                'Failed to head Block {0:} from BlockStorage, Vault {1:}'
                'Error ({2:}): {3:}'.format(block.storage_id, vault.vault_id,
                                            res.status_code,
                                            res.text))

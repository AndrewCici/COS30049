import { Button, Stack, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <Stack spacing={2} sx={{ py: 6, alignItems: 'flex-start' }}>
      <Typography variant="h3" component="h1">
        Page not found
      </Typography>
      <Typography color="text.secondary">
        There is nothing at this address. The detector is on the home page.
      </Typography>
      <Button component={RouterLink} to="/" variant="contained">
        Back to the detector
      </Button>
    </Stack>
  );
}
